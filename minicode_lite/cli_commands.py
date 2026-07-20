from __future__ import annotations

"""把 session、checkpoint、memory 等内部能力暴露为无需模型参与的本地命令。"""

from pathlib import Path
from typing import Any

from minicode_lite.memory import MemoryManager
from minicode_lite.readiness import (
    build_readiness_report,
    format_readiness_json,
    format_readiness_text,
)
from minicode_lite.session import (
    SessionData,
    SessionMetadata,
    format_rewind_preview,
    format_session_checkpoints,
    format_session_inspect,
    format_session_replay,
    get_latest_session,
    list_sessions,
    load_session,
    rewind_session_data,
)
from minicode_lite.tooling import ToolContext, ToolRegistry


def format_tools(tools: ToolRegistry) -> str:
    """把当前注册表转成稳定、适合终端显示的“名称: 描述”列表。"""

    # 注册表顺序就是默认工具的教学顺序，不能在展示层重新排序。
    definitions = tools.list()
    if not definitions:
        # 空注册表是可诊断状态，不应只返回一个难以理解的空字符串。
        return "No tools registered."
    return "\n".join(f"{tool.name}: {tool.description}" for tool in definitions)


def format_session_list(sessions: list[SessionMetadata]) -> str:
    """把当前 workspace 的会话摘要格式化为从新到旧的紧凑列表。"""

    if not sessions:
        return "No saved sessions found for this workspace."
    lines = ["Saved sessions:"]
    for metadata in sessions:
        # 首条用户消息帮助识别任务；空会话用固定占位符保持每行结构稳定。
        summary = metadata.first_message or "(no user message)"
        lines.append(
            f"- {metadata.session_id}: {summary} "
            f"({metadata.message_count} messages, {metadata.checkpoint_count} checkpoints)"
        )
    lines.append(f"Total: {len(sessions)} session(s)")
    return "\n".join(lines)


def format_memory_status(memory: MemoryManager) -> str:
    """展示 memory 的工作区、持久化位置和条目数量，不创建新文件。"""

    # 文件是否存在与条目数量分开显示，能区分“尚未写入”和“损坏后降级为空”。
    storage_status = "present" if memory.memory_file.is_file() else "not created"
    return "\n".join(
        [
            "Project memory:",
            f"Workspace: {memory.workspace}",
            f"Storage: {memory.memory_file} ({storage_status})",
            f"Entries: {len(memory.entries)}",
        ]
    )


def _resolve_session(
    target: str,
    *,
    cwd: str | Path,
    active_session: SessionData | None,
) -> SessionData | None:
    """在工作区边界内解析 active、latest 或显式 session ID。"""

    workspace = Path(cwd).resolve()
    if target in {"", "latest"}:
        # 交互式入口传入的 live session 比磁盘记录更新，应优先使用。
        if active_session is not None and Path(active_session.workspace).resolve() == workspace:
            return active_session
        return get_latest_session(workspace=workspace)
    if (
        active_session is not None
        and target == active_session.session_id
        and Path(active_session.workspace).resolve() == workspace
    ):
        return active_session
    try:
        candidate = load_session(target)
    except ValueError:
        # session ID 校验属于产品输入边界，非法路径片段不能扩散成 traceback。
        return None
    if candidate is None:
        return None
    # 显式 ID 也必须属于当前 workspace，避免产品命令跨项目查看或回退文件。
    if Path(candidate.workspace).resolve() != workspace:
        return None
    return candidate


def _parse_rewind_target(argument: str) -> tuple[int, str | None] | None:
    """把 latest、正整数步数或 checkpoint ID 转成 session API 参数。"""

    if not argument or argument == "latest":
        return 1, None
    if argument.isdigit():
        steps = int(argument)
        # 零步没有清晰的产品语义，明确返回用法提示比静默改成一步更可预测。
        return (steps, None) if steps > 0 else None
    # checkpoint ID 的合法性最终由 session 数据匹配；命令层只负责分流两种参数形态。
    return 1, argument


def _format_rewind_result(session: SessionData, restored_count: int) -> str:
    """格式化成功回退后的摘要，并提示反向 checkpoint 已被保留。"""

    return "\n".join(
        [
            f"Rewound {restored_count} checkpoint(s) for session {session.session_id}.",
            "A reverse checkpoint was saved, so the rewind can be undone.",
            f"Remaining checkpoints: {len(session.checkpoints)}",
        ]
    )


def try_handle_local_command(
    user_input: str,
    *,
    tools: ToolRegistry,
    cwd: str | Path,
    permissions: Any | None = None,
    session: SessionData | None = None,
) -> str | None:
    """执行已知本地命令；返回 None 表示输入应进入 agent loop。"""

    # 统一去除边界空白，命令名和参数之间再用一次 split 形成稳定语法。
    text = user_input.strip()
    if not text.startswith("/"):
        return None
    command, _, argument = text.partition(" ")
    argument = argument.strip()
    workspace = Path(cwd).resolve()

    if command == "/tools" and not argument:
        return format_tools(tools)
    if command == "/tools":
        return "Usage: /tools"

    if command == "/readiness" and argument in {"", "--json"}:
        # readiness 只读取本地环境和配置，不创建模型，也不发起 provider 请求。
        report = build_readiness_report(workspace, tools)
        return format_readiness_json(report) if argument == "--json" else format_readiness_text(report)
    if command == "/readiness":
        return "Usage: /readiness [--json]"

    if command == "/read":
        if not argument:
            return "Usage: /read <path>"
        # 快捷命令复用 agent loop 的工具上下文，路径和权限规则不会产生第二套实现。
        result = tools.execute(
            "read_file",
            {"path": argument},
            ToolContext(cwd=str(workspace), permissions=permissions),
        )
        return result.output

    if command == "/sessions" and not argument:
        return format_session_list(list_sessions(workspace=workspace))
    if command == "/sessions":
        return "Usage: /sessions"

    if command in {"/session", "/session-replay", "/checkpoints"}:
        # 这三个只读命令共享 session 解析规则，并允许显式选择 ID 或 latest。
        if argument and " " in argument:
            return f"Usage: {command} [session-id|latest]"
        target_session = _resolve_session(
            argument,
            cwd=workspace,
            active_session=session,
        )
        if target_session is None:
            return "No saved session found for this workspace."
        if command == "/session":
            return format_session_inspect(target_session)
        if command == "/session-replay":
            return format_session_replay(target_session)
        return format_session_checkpoints(target_session)

    if command in {"/rewind-preview", "/rewind"}:
        if " " in argument:
            return f"Usage: {command} [latest|steps|checkpoint-id]"
        parsed = _parse_rewind_target(argument)
        if parsed is None:
            return f"Usage: {command} [latest|steps|checkpoint-id]"
        target_session = _resolve_session("latest", cwd=workspace, active_session=session)
        if target_session is None:
            return "No saved session found for this workspace."
        steps, checkpoint_id = parsed
        if command == "/rewind-preview":
            # preview 只调用选择与格式化逻辑，不读取或修改目标文件。
            return format_rewind_preview(
                target_session,
                steps=steps,
                checkpoint_id=checkpoint_id,
            )
        restored = rewind_session_data(
            target_session,
            steps=steps,
            checkpoint_id=checkpoint_id,
        )
        if not restored:
            return f"No checkpoints available to rewind for session {target_session.session_id}."
        return _format_rewind_result(target_session, len(restored))

    if command == "/memory" and not argument:
        return format_memory_status(MemoryManager(workspace))
    if command == "/memory":
        return "Usage: /memory"

    # 只识别本阶段明确拥有的命令；未知 slash 输入仍可作为普通用户任务交给模型理解。
    return None


__all__ = [
    "format_memory_status",
    "format_readiness_json",
    "format_readiness_text",
    "format_session_list",
    "format_tools",
    "try_handle_local_command",
]
