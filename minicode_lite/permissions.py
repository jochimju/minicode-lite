from __future__ import annotations

"""提供阶段 7 的最小权限策略：工作区路径、文件编辑和命令审批。"""

import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal


# 审批结果保持为小而明确的集合，避免 prompt handler 返回任意文本后被误判为放行。
PermissionDecision = Literal[
    "allow_once",
    "allow_turn",
    "allow_all_turn",
    "deny_once",
]
# 展示层接收结构化请求并返回决策；测试可直接注入 lambda，无需真实终端交互。
PromptHandler = Callable[[dict[str, Any]], dict[str, Any] | PermissionDecision]


def _normalize_path(path: str | Path) -> str:
    """解析绝对路径、点段和符号链接，得到权限比较使用的唯一形态。"""

    # strict=False 允许在新文件尚不存在时也完成规范化，这是写文件审批的必要边界。
    return str(Path(path).resolve(strict=False))


def _is_within_directory(root: str, target: str) -> bool:
    """判断 target 是否位于 root 内，并在 Windows 上按大小写不敏感语义比较。"""

    # normcase 在 Windows 会同时统一分隔符和大小写，符合常见 NTFS 路径语义。
    normalized_root = os.path.normcase(root)
    normalized_target = os.path.normcase(target)
    try:
        # commonpath 按路径段比较，避免 `repo-other` 被误认为 `repo` 的子目录。
        return os.path.commonpath([normalized_root, normalized_target]) == normalized_root
    except ValueError:
        # Windows 不同盘符没有公共路径；这种情况必须视为工作区外访问。
        return False


def _command_signature(command: str, args: list[str]) -> str:
    """生成供审批界面和 turn 缓存使用的稳定命令签名。"""

    # 参数已由工具校验为字符串，这里只负责组合成人可读的一行。
    return " ".join([command, *args]).strip()


def classify_dangerous_command(command: str, args: list[str]) -> str | None:
    """识别少量高风险命令模式；返回原因表示必须进入审批。"""

    # Windows 命令名大小写不敏感；统一小写也让跨平台测试保持一致。
    executable = Path(command).name.lower()
    # 保留参数边界做精确规则判断，同时构造小写文本识别 shell 载荷。
    lowered_args = [arg.lower() for arg in args]
    signature = _command_signature(executable, lowered_args)

    if executable == "git":
        # 这些 git 操作可能覆盖本地修改、删除未跟踪文件或改写远端历史。
        if "reset" in lowered_args and "--hard" in lowered_args:
            return f"git reset --hard can discard local changes ({signature})"
        if "clean" in lowered_args:
            return f"git clean can delete untracked files ({signature})"
        if "push" in lowered_args and any(arg in {"--force", "-f"} for arg in lowered_args):
            return f"git push --force can rewrite remote history ({signature})"

    if executable in {"rm", "del", "erase", "rmdir", "rd"}:
        # 删除命令即使目标看似位于 cwd，也需要人确认具体范围。
        return f"delete command can remove files or directories ({signature})"
    if executable in {"format", "mkfs", "diskpart", "dd"}:
        # 磁盘级命令的影响远超当前工作区，不能自动执行。
        return f"disk command can destroy data ({signature})"
    if executable in {"python", "python3", "node", "powershell", "pwsh", "cmd", "sh", "bash"}:
        # 解释器能够绕过工具自己的文件边界执行任意代码，因此始终审批。
        return f"interpreter can execute arbitrary code ({signature})"
    return None


def classify_shell_snippet(command_line: str) -> str | None:
    """识别依赖 shell 解释的复合命令，并标出特别危险的下载执行模式。"""

    # 压缩空白后再匹配，防止简单换行或多空格绕过风险规则。
    collapsed = re.sub(r"\s+", " ", command_line.lower()).strip()
    if re.search(r"\b(curl|wget)\b.*\|\s*(sh|bash)\b", collapsed):
        return "shell snippet downloads and executes a script"
    if re.search(
        r"\b(iwr|irm|invoke-webrequest|invoke-restmethod|curl|wget)\b.*\|\s*(iex|invoke-expression)\b",
        collapsed,
    ):
        return "shell snippet downloads and executes PowerShell code"
    if re.search(r"\brm\s+-[a-z]*r[a-z]*f\b|\brm\s+-[a-z]*f[a-z]*r\b", collapsed):
        return "shell snippet contains recursive forced deletion"
    # 任意 shell 控制符都会改变单一 argv 的语义，至少需要一次明确审批。
    if any(character in command_line for character in "|&;<>()$`"):
        return "shell control operators can execute multiple commands"
    if os.name == "nt" and any(character in command_line for character in "^%!"):
        # cmd.exe 会处理转义符、环境变量和延迟展开；看似普通的 echo 参数也可能被改写。
        return "Windows shell expansion can reinterpret command text"
    return None


class PermissionManager:
    """集中管理路径、编辑和命令的最小审批状态。"""

    def __init__(self, workspace_root: str | Path, prompt_handler: PromptHandler | None = None) -> None:
        # 工作区根只在构造时规范化，后续每次检查都与同一基准比较。
        self.workspace_root = _normalize_path(workspace_root)
        # None 表示当前运行面没有交互能力，高风险行为将采用默认拒绝。
        self.prompt_handler = prompt_handler
        # turn 级集合只缓存用户明确选择的本轮授权，不跨会话持久化。
        self._turn_allowed_paths: set[str] = set()
        self._turn_allowed_edits: set[str] = set()
        self._turn_allowed_commands: set[str] = set()
        self._turn_allow_all_paths = False
        self._turn_allow_all_edits = False
        self._turn_allow_all_commands = False

    def begin_turn(self) -> None:
        """开始新一轮时清空上一轮的临时授权。"""

        self._turn_allowed_paths.clear()
        self._turn_allowed_edits.clear()
        self._turn_allowed_commands.clear()
        self._turn_allow_all_paths = False
        self._turn_allow_all_edits = False
        self._turn_allow_all_commands = False

    def end_turn(self) -> None:
        """结束一轮并立即撤销 turn 级授权。"""

        self.begin_turn()

    def get_summary(self) -> list[str]:
        """返回可注入 system prompt 的非敏感策略摘要。"""

        return [
            f"workspace: {self.workspace_root}",
            "workspace reads are allowed",
            "external paths, file edits, and non-read-only commands require approval",
        ]

    def _request(self, request: dict[str, Any]) -> PermissionDecision:
        """调用注入的审批器，并把缺失或未知返回值安全地归一化为拒绝。"""

        if self.prompt_handler is None:
            # headless 没有用户可确认时不能猜测同意，这是权限系统的 fail-closed 默认值。
            return "deny_once"
        response = self.prompt_handler(request)
        # 测试或简单 UI 可直接返回字符串，完整 UI 则可返回带 decision 的字典。
        decision = response.get("decision") if isinstance(response, dict) else response
        if decision in {"allow_once", "allow_turn", "allow_all_turn", "deny_once"}:
            return decision
        # 未知决策不得意外放行。
        return "deny_once"

    def ensure_path_access(self, target_path: str, intent: str) -> None:
        """允许 cwd 内访问；cwd 外访问必须得到 prompt handler 明确批准。"""

        normalized_target = _normalize_path(target_path)
        if _is_within_directory(self.workspace_root, normalized_target):
            # 工作区内路径已由规范化比较保护，可继续进入文件工具。
            return
        if self._turn_allow_all_paths or normalized_target in self._turn_allowed_paths:
            # 只复用用户在当前 turn 内明确给出的外部路径授权。
            return
        decision = self._request(
            {
                "kind": "path",
                "summary": f"MiniCode Lite requests {intent} access outside the workspace.",
                "details": [
                    f"workspace: {self.workspace_root}",
                    f"target: {normalized_target}",
                ],
                "scope": normalized_target,
            }
        )
        if decision == "allow_once":
            return
        if decision == "allow_turn":
            self._turn_allowed_paths.add(normalized_target)
            return
        if decision == "allow_all_turn":
            self._turn_allow_all_paths = True
            return
        raise PermissionError(f"Path access denied outside workspace: {normalized_target}")

    def ensure_edit(self, target_path: str, diff_preview: str) -> None:
        """在文件真正写盘前审批修改，并支持单文件或全体编辑的 turn 授权。"""

        normalized_target = _normalize_path(target_path)
        # 编辑审批不能替代路径检查；先保证目标本身没有绕开 workspace 边界。
        self.ensure_path_access(normalized_target, "write")
        if self._turn_allow_all_edits or normalized_target in self._turn_allowed_edits:
            return
        decision = self._request(
            {
                "kind": "edit",
                "summary": "MiniCode Lite requests permission to modify a file.",
                "details": [f"target: {normalized_target}", diff_preview],
                "scope": normalized_target,
            }
        )
        if decision == "allow_once":
            return
        if decision == "allow_turn":
            self._turn_allowed_edits.add(normalized_target)
            return
        if decision == "allow_all_turn":
            self._turn_allow_all_edits = True
            return
        raise PermissionError(f"Edit denied: {normalized_target}")

    def ensure_command(
        self,
        command: str,
        args: list[str],
        command_cwd: str,
        force_prompt_reason: str | None = None,
    ) -> None:
        """审批非只读或危险命令；调用方负责只读命令的快速放行。"""

        normalized_cwd = _normalize_path(command_cwd)
        # 即便命令本身获批，也不能借 cwd 参数静默逃逸工作区。
        self.ensure_path_access(normalized_cwd, "command_cwd")
        signature = _command_signature(command, args)
        if self._turn_allow_all_commands or signature in self._turn_allowed_commands:
            return
        reason = force_prompt_reason or classify_dangerous_command(command, args)
        decision = self._request(
            {
                "kind": "command",
                "summary": "MiniCode Lite requests permission to run a command.",
                "details": [
                    f"cwd: {normalized_cwd}",
                    f"command: {signature}",
                    f"reason: {reason or 'command is not in the read-only allowlist'}",
                ],
                "scope": signature,
            }
        )
        if decision == "allow_once":
            return
        if decision == "allow_turn":
            self._turn_allowed_commands.add(signature)
            return
        if decision == "allow_all_turn":
            self._turn_allow_all_commands = True
            return
        raise PermissionError(f"Command denied: {signature}")


__all__ = [
    "PermissionDecision",
    "PermissionManager",
    "PromptHandler",
    "classify_dangerous_command",
    "classify_shell_snippet",
]
