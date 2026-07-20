from __future__ import annotations

# 提供非交互式单轮入口，适合命令行脚本、CI smoke 和最小演示。

import argparse
from pathlib import Path
from typing import TextIO

from minicode_lite.agent_loop import run_agent_turn
from minicode_lite.config import load_runtime_config
from minicode_lite.cli_commands import try_handle_local_command
from minicode_lite.memory import MemoryManager
from minicode_lite.model_registry import create_model_adapter
from minicode_lite.permissions import PermissionManager
from minicode_lite.prompt import build_system_prompt
from minicode_lite.session import create_new_session, save_session
from minicode_lite.tools import create_default_tool_registry
from minicode_lite.types import ChatMessage


def _last_assistant_content(messages: list[ChatMessage]) -> str:
    """从最终历史中提取最近 assistant 文本，作为 headless 的唯一输出。"""

    # 反向扫描可忽略中间的工具调用、工具结果和进度消息。
    for message in reversed(messages):
        if message.get("role") == "assistant":
            # content 缺失时仍返回空字符串，保持提取函数总是返回 str。
            return message.get("content", "")
    # 防御性兜底：模型未产生最终回答时仍给命令行可见结果。
    return "(no response)"


def run_headless(prompt: str, *, cwd: str | Path | None = None) -> str:
    """在指定工作区执行一个 prompt，并返回本地命令结果或最终 assistant 文本。"""

    # 提前清理空白，避免空任务进入模型和工具循环。
    user_prompt = prompt.strip()
    if not user_prompt:
        # 作为可预期的调用错误交给 CLI 层格式化为退出码和错误信息。
        raise ValueError("empty prompt")

    # 未指定 cwd 时使用当前目录，使函数既可被 CLI 调用也方便测试注入临时目录。
    workspace = Path.cwd() if cwd is None else Path(cwd)
    # 每个 headless turn 构造干净的默认工具注册表，不携带上次调用的状态。
    tools = create_default_tool_registry()
    # headless 没有交互审批界面，因此权限管理器对编辑和非只读命令采用默认拒绝。
    permissions = PermissionManager(workspace)
    # 项目记忆与 workspace 一一绑定；检索只读，不会为没有记忆的项目创建目录。
    memory = MemoryManager(workspace)

    # `/tools`、`/read` 等本地命令无需消耗模型调用，优先直接分流处理。
    local_result = try_handle_local_command(
        user_prompt,
        tools=tools,
        cwd=workspace,
        permissions=permissions,
    )
    if local_result is not None:
        return local_result

    # 本地命令已经提前返回；只有需要模型推理时才读取配置，避免 `/tools` 等命令依赖 provider 环境。
    config = load_runtime_config()
    # 注册表以完整性判断选择真实或 mock 适配器，并确保真实适配器持有本轮的同一份工具定义。
    model, _diagnostic = create_model_adapter(config, tools)
    # system 消息必须在用户任务之前，使模型先获得工作区、工具清单和当前能力边界。
    messages: list[ChatMessage] = [
        {
            "role": "system",
            "content": build_system_prompt(
                cwd=str(workspace),
                tools=tools,
                permissions=permissions,
                memory_context=memory.get_context(user_prompt),
            ),
        },
        {"role": "user", "content": user_prompt},
    ]
    # 每个真实模型 turn 都创建独立 session；本地只读命令没有 agent 消息循环，因此不落 session。
    session = create_new_session(workspace=workspace)
    session.messages = [dict(message) for message in messages]
    try:
        result_messages = run_agent_turn(
            model=model,
            tools=tools,
            messages=messages,
            cwd=str(workspace),
            permissions=permissions,
            session=session,
        )
        # 成功时用 loop 返回的完整历史替换输入快照，使工具请求、结果和最终回答全部可回放。
        session.messages = [dict(message) for message in result_messages]
    finally:
        # provider 或工具路径抛出异常时仍保留已经建立的输入记录，便于事后定位失败 turn。
        save_session(session)
    # headless 只暴露本轮最终回答，不泄漏内部消息协议给命令行用户。
    return _last_assistant_content(result_messages)


def build_parser() -> argparse.ArgumentParser:
    """构建 headless 专用参数解析器，便于测试独立验证参数行为。"""

    parser = argparse.ArgumentParser(
        prog="minicode-lite-headless",
        description="Run one non-interactive MiniCode Lite turn.",
    )
    # 使用可变位置参数，让多个命令行词组在稍后重新拼成一个 prompt。
    parser.add_argument("prompt", nargs="*", help="Prompt to send to the mock agent.")
    # 作为独立选项接收后再还原到本地命令，避免 argparse 把 `/readiness --json` 当成未知参数拒绝。
    parser.add_argument("--json", action="store_true", help="Render the /readiness command as JSON.")
    return parser


def run(argv: list[str] | None = None, stdout: TextIO | None = None, stderr: TextIO | None = None) -> int:
    """解析参数、运行单轮任务，并以整数退出码表达命令行结果。"""

    parser = build_parser()
    args = parser.parse_args(argv)

    # 延迟导入仅在调用时需要的标准流，测试可传入 StringIO 避免捕获全局输出。
    import sys

    # 注入流优先，未注入时回退到真实命令行标准输出和标准错误。
    out = sys.stdout if stdout is None else stdout
    err = sys.stderr if stderr is None else stderr
    # argparse 把位置参数拆成列表；用空格重建用户原本的单条提示。
    prompt = " ".join(args.prompt).strip()
    if args.json:
        if prompt != "/readiness":
            print("Error: --json is only valid with /readiness", file=err)
            return 1
        prompt += " --json"
    if not prompt:
        print("Error: empty prompt", file=err)
        return 1

    try:
        # 成功路径只打印最终文本，保持 headless 输出适合脚本消费。
        print(run_headless(prompt), file=out)
    except RuntimeError:
        # provider 异常文本可能含有请求头或响应正文；统一替换为固定提示，防止认证信息进入终端或 CI 日志。
        print("Error: model provider request failed", file=err)
        return 1
    except ValueError as error:
        # 参数校验错误不携带 provider 敏感信息，保留具体内容可帮助用户修正命令行输入。
        print(f"Error: {error}", file=err)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    """供 console script 调用的薄入口，便于保持 run 函数可注入和可测试。"""

    return run(argv)
