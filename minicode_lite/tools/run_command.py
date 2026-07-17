from __future__ import annotations

"""执行受权限边界保护的前台命令，并限制运行时间和返回上下文大小。"""

import locale
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any, Sequence

from minicode_lite.permissions import classify_dangerous_command, classify_shell_snippet
from minicode_lite.tooling import ToolContext, ToolDefinition, ToolResult
from minicode_lite.workspace import resolve_tool_path


# 默认超时保持较短，避免一次模型调用长期占住 agent loop；调用方可在安全范围内覆盖。
DEFAULT_TIMEOUT_SECONDS = 30
# 工具输出会进入模型上下文，必须设置硬上限避免日志洪泛。
MAX_OUTPUT_CHARS = 20_000

# 只包含不会按正常语义修改文件或外部状态的常用查看命令。
READ_ONLY_COMMANDS = {
    "cat",
    "dir",
    "echo",
    "findstr",
    "grep",
    "head",
    "hostname",
    "ls",
    "more",
    "pwd",
    "rg",
    "tail",
    "type",
    "wc",
    "where",
    "whoami",
}
# git 的这些子命令用于观察仓库；其余 git 行为仍进入审批。
READ_ONLY_GIT_SUBCOMMANDS = {"diff", "log", "show", "status"}
# Windows 内建命令不能直接通过 CreateProcess 启动，需要显式委托给 cmd.exe。
WINDOWS_SHELL_BUILTINS = {"dir", "echo", "type", "where"}


def split_command_line(command_line: str) -> list[str]:
    """按当前平台规则拆分简短命令行，同时保留 Windows 路径中的反斜杠。"""

    try:
        # posix=False 避免 `C:\path` 中的反斜杠被当作转义符吞掉。
        return shlex.split(command_line, posix=os.name != "nt")
    except ValueError:
        # 未闭合引号属于输入错误，交给 validator/runner 返回可恢复失败。
        return []


def _normalize_command_input(input_data: dict[str, Any]) -> tuple[str, list[str]]:
    """把 `command` 字符串和可选 `args` 统一为 executable + argv。"""

    raw_command = input_data["command"].strip()
    # runner 也接受测试直接调用 ToolDefinition.run 的路径，因此为可选字段保留默认值。
    raw_args = input_data.get("args") or []
    if raw_args:
        # 显式 args 已经表达参数边界，command 此时只作为可执行文件名解释。
        return raw_command, list(raw_args)
    parsed = split_command_line(raw_command)
    if not parsed:
        return "", []
    return parsed[0], parsed[1:]


def _is_read_only_command(command: str, args: list[str]) -> bool:
    """判断一组 argv 是否属于无需审批的保守只读集合。"""

    executable = Path(command).name.lower()
    if executable in READ_ONLY_COMMANDS:
        return True
    # git 只有明确列出的观察型子命令免审批，缺少子命令时仍需确认。
    return executable == "git" and bool(args) and args[0].lower() in READ_ONLY_GIT_SUBCOMMANDS


def _build_execution_command(
    raw_command: str,
    command: str,
    args: Sequence[str],
    *,
    use_shell: bool,
) -> list[str]:
    """构造 shell=False 可执行的 argv，避免普通命令经过不必要的 shell 解析。"""

    if use_shell:
        # 复合命令已经经过强制审批；这里才允许 shell 解释控制符。
        if os.name == "nt":
            return ["cmd", "/d", "/s", "/c", raw_command]
        return [os.environ.get("SHELL", "/bin/sh"), "-lc", raw_command]
    executable = Path(command).name.lower()
    if os.name == "nt" and executable in WINDOWS_SHELL_BUILTINS:
        # list2cmdline 正确引用每个参数，防止普通参数意外变成 cmd 控制符。
        joined_args = subprocess.list2cmdline(list(args))
        builtin_line = command if not joined_args else f"{command} {joined_args}"
        return ["cmd", "/d", "/s", "/c", builtin_line]
    return [command, *args]


def _decode_output(data: bytes | str | None) -> str:
    """以本机首选编码解码命令输出，失败时使用替换字符而不是抛异常。"""

    if not data:
        return ""
    if isinstance(data, str):
        return data
    # Windows 传统命令常使用本地代码页，locale 比固定 UTF-8 更贴近真实终端。
    encoding = locale.getpreferredencoding(False) or "utf-8"
    return data.decode(encoding, errors="replace")


def _truncate_output(output: str, max_chars: int = MAX_OUTPUT_CHARS) -> str:
    """保留输出头尾并标记省略量，让错误末尾和启动上下文都可见。"""

    if len(output) <= max_chars:
        return output
    # 头部保留约六成、尾部保留约四成，中间插入明确的截断标记。
    head_size = max_chars * 3 // 5
    tail_size = max_chars - head_size
    omitted = len(output) - max_chars
    return f"{output[:head_size]}\n... [{omitted} chars omitted] ...\n{output[-tail_size:]}"


def _validate(input_data: Any) -> dict[str, Any]:
    """校验命令、参数、工作目录和超时，返回 runner 使用的稳定结构。"""

    if not isinstance(input_data, dict):
        raise ValueError("input must be an object")
    command = input_data.get("command")
    if not isinstance(command, str) or not command.strip():
        raise ValueError("command is required")
    args = input_data.get("args", [])
    if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
        raise ValueError("args must be a list of strings")
    cwd = input_data.get("cwd")
    if cwd is not None and not isinstance(cwd, str):
        raise ValueError("cwd must be a string")
    timeout = input_data.get("timeout", DEFAULT_TIMEOUT_SECONDS)
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool):
        raise ValueError("timeout must be a number")
    # 上下界阻止零超时误用，也避免单次工具调用无限占用运行时。
    timeout_seconds = max(1, min(300, float(timeout)))
    return {"command": command, "args": args, "cwd": cwd, "timeout": timeout_seconds}


def _run(input_data: dict[str, Any], context: ToolContext) -> ToolResult:
    """完成路径和命令审批后执行进程，并返回合并后的 stdout/stderr。"""

    try:
        # 自定义 cwd 与文件工具共用同一个规范化入口，不能借命令参数逃出工作区。
        effective_cwd = (
            resolve_tool_path(context, input_data.get("cwd"), "command_cwd")
            if input_data.get("cwd")
            else resolve_tool_path(context, ".", "command_cwd")
        )
    except PermissionError as error:
        return ToolResult(ok=False, output=str(error))

    command, args = _normalize_command_input(input_data)
    if not command:
        return ToolResult(ok=False, output="Command not allowed: invalid command line")

    # 只有未提供显式 args 时，command 字符串才可能是一段复合 shell 语句。
    use_shell = not input_data.get("args") and classify_shell_snippet(input_data["command"]) is not None
    shell_reason = classify_shell_snippet(input_data["command"]) if use_shell else None
    dangerous_reason = classify_dangerous_command(command, args)
    needs_approval = use_shell or dangerous_reason is not None or not _is_read_only_command(command, args)

    if needs_approval:
        if context.permissions is None:
            # 没有权限系统时仍需 fail closed，不能把“未配置”解释为“全部允许”。
            return ToolResult(ok=False, output=f"Command requires approval: {command}")
        try:
            context.permissions.ensure_command(
                command,
                args,
                str(effective_cwd),
                force_prompt_reason=shell_reason or dangerous_reason,
            )
        except PermissionError as error:
            return ToolResult(ok=False, output=str(error))

    execution_argv = _build_execution_command(
        input_data["command"],
        command,
        args,
        use_shell=use_shell,
    )
    try:
        # shell=False 是常规路径的关键安全边界；只有上方审批过的复合命令才显式启动 shell。
        completed = subprocess.run(
            execution_argv,
            cwd=str(effective_cwd),
            capture_output=True,
            check=False,
            timeout=input_data.get("timeout", DEFAULT_TIMEOUT_SECONDS),
            shell=False,
        )
    except subprocess.TimeoutExpired as error:
        partial = "\n".join(
            part
            for part in (_decode_output(error.stdout).strip(), _decode_output(error.stderr).strip())
            if part
        )
        suffix = f"\nPartial output:\n{_truncate_output(partial)}" if partial else ""
        return ToolResult(
            ok=False,
            output=(
                f"Command timed out after "
                f"{input_data.get('timeout', DEFAULT_TIMEOUT_SECONDS):g} seconds.{suffix}"
            ),
        )
    except FileNotFoundError:
        return ToolResult(ok=False, output=f"Command not found: {command}")
    except OSError as error:
        return ToolResult(ok=False, output=f"Could not run command: {error}")

    output = "\n".join(
        part
        for part in (
            _decode_output(completed.stdout).strip(),
            _decode_output(completed.stderr).strip(),
        )
        if part
    )
    # 非零退出码通过 ok=False 表达；输出保持原样供模型诊断下一步。
    return ToolResult(ok=completed.returncode == 0, output=_truncate_output(output))


run_command_tool = ToolDefinition(
    name="run_command",
    description="Run a foreground command with permission checks, timeout, and output limits.",
    input_schema={
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "args": {"type": "array", "items": {"type": "string"}},
            "cwd": {"type": "string"},
            "timeout": {"type": "number", "minimum": 1, "maximum": 300},
        },
        "required": ["command"],
    },
    validator=_validate,
    run=_run,
)


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "MAX_OUTPUT_CHARS",
    "run_command_tool",
    "split_command_line",
]
