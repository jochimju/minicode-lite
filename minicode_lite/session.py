from __future__ import annotations

# 负责把一次 agent turn 的消息和可读时间线保存为可检查、可回放的 JSON 文件。

import json
import os
import re
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from minicode_lite.types import ChatMessage


# 环境变量方便部署选择持久目录；默认使用系统用户临时区，兼容主目录只读的受限运行环境。
SESSIONS_DIR = Path(
    os.environ.get("MINICODE_LITE_SESSIONS_DIR")
    or Path(tempfile.gettempdir()) / "minicode-lite" / "sessions"
)
# 文件名只接受这一组安全字符，防止外部 session_id 被解释成目录穿越路径。
_SAFE_SESSION_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


@dataclass(slots=True)
class SessionMetadata:
    """供 session 列举使用的轻量摘要，不需要调用方读取完整 JSON 结构。"""

    session_id: str
    created_at: float
    updated_at: float
    workspace: str
    first_message: str = ""
    message_count: int = 0
    transcript_count: int = 0


@dataclass(slots=True)
class SessionData:
    """一份可持久化会话的完整状态：原始消息、可读 transcript 和摘要。"""

    session_id: str
    created_at: float
    updated_at: float
    workspace: str
    messages: list[ChatMessage] = field(default_factory=list)
    transcript_entries: list[dict[str, Any]] = field(default_factory=list)
    metadata: SessionMetadata | None = None

    def update_metadata(self) -> None:
        """根据当前权威状态刷新时间和摘要，避免调用方手工同步重复字段。"""

        # 保存发生的时刻就是最后更新时间；created_at 始终保持首次创建时间。
        self.updated_at = time.time()
        first_message = ""
        # 首条用户消息最能帮助列表页识别会话；system prompt 不作为标题。
        for message in self.messages:
            if message.get("role") == "user":
                content = message.get("content", "")
                first_message = content if isinstance(content, str) else str(content)
                break
        self.metadata = SessionMetadata(
            session_id=self.session_id,
            created_at=self.created_at,
            updated_at=self.updated_at,
            workspace=self.workspace,
            # 摘要限制长度，完整内容仍只保留在 messages 中。
            first_message=first_message[:100],
            message_count=len(self.messages),
            transcript_count=len(self.transcript_entries),
        )


def _resolved_workspace(workspace: str | Path) -> str:
    """把工作区存为稳定绝对路径，使 Windows 大小写和相对路径过滤行为一致。"""

    return str(Path(workspace).resolve())


def _session_file(session_id: str) -> Path:
    """校验外部 ID 后生成文件路径，拒绝用 session API 读取目录外文件。"""

    if _SAFE_SESSION_ID.fullmatch(session_id) is None:
        raise ValueError("invalid session id")
    return SESSIONS_DIR / f"{session_id}.json"


def _copy_messages(messages: list[ChatMessage]) -> list[ChatMessage]:
    """复制消息字典，让 session 状态不与 agent loop 返回列表共享顶层对象。"""

    return [dict(message) for message in messages]


def build_transcript(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    """从权威消息历史派生适合人类回放的时间线，输入消息保持不变。"""

    entries: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        # system prompt 属于运行配置而非对话事件；messages 会保留它，replay 则聚焦实际 turn。
        if role == "system":
            continue
        entry: dict[str, Any] = {
            "id": len(entries) + 1,
            "kind": role or "unknown",
            "body": message.get("content", ""),
        }
        # 工具名和调用 ID 让请求与结果无需回看原始消息也能正确配对。
        if role in {"assistant_tool_call", "tool_result"}:
            entry["toolName"] = message.get("toolName", "")
            entry["toolUseId"] = message.get("toolUseId", "")
        if role == "assistant_tool_call":
            # input 保持结构化，inspect/replay 可读，未来 checkpoint 也能消费原始参数。
            entry["input"] = message.get("input")
        if role == "tool_result":
            entry["isError"] = bool(message.get("isError", False))
        entries.append(entry)
    return entries


def create_new_session(workspace: str | Path) -> SessionData:
    """创建空 session；真正写盘由 save_session 显式完成，便于先填充完整 turn。"""

    now = time.time()
    session = SessionData(
        session_id=uuid.uuid4().hex[:12],
        created_at=now,
        updated_at=now,
        workspace=_resolved_workspace(workspace),
    )
    session.update_metadata()
    return session


def save_session(session: SessionData) -> Path:
    """以完整 JSON 快照保存 session，并返回最终文件路径。"""

    # transcript 是 messages 的展示投影，每次保存都重新生成以消除双写漂移。
    session.messages = _copy_messages(session.messages)
    session.transcript_entries = build_transcript(session.messages)
    session.update_metadata()
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    target = _session_file(session.session_id)
    payload = {
        "schema_version": 1,
        "session_id": session.session_id,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "workspace": session.workspace,
        "messages": session.messages,
        "transcript_entries": session.transcript_entries,
        "metadata": asdict(session.metadata) if session.metadata is not None else None,
    }
    # 先写同目录临时文件再替换，避免进程中断留下半截 JSON。
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)
    return target


def load_session(session_id: str) -> SessionData | None:
    """读取并校验 session；文件不存在或内容损坏时返回 None。"""

    path = _session_file(session_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema_version") != 1 or data.get("session_id") != session_id:
            return None
        metadata_data = data.get("metadata")
        metadata = SessionMetadata(**metadata_data) if isinstance(metadata_data, dict) else None
        session = SessionData(
            session_id=data["session_id"],
            created_at=float(data["created_at"]),
            updated_at=float(data["updated_at"]),
            workspace=str(data["workspace"]),
            messages=_copy_messages(data.get("messages", [])),
            transcript_entries=[dict(entry) for entry in data.get("transcript_entries", [])],
            metadata=metadata,
        )
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        # 历史损坏不能阻塞其他 session 的列举；调用方用 None 展示不可恢复状态。
        return None
    return session


def list_sessions(workspace: str | Path | None = None) -> list[SessionMetadata]:
    """列举可加载 session，可按规范化工作区过滤，并按最近更新倒序排列。"""

    if not SESSIONS_DIR.is_dir():
        return []
    expected_workspace = _resolved_workspace(workspace) if workspace is not None else None
    sessions: list[SessionMetadata] = []
    for path in SESSIONS_DIR.glob("*.json"):
        try:
            session = load_session(path.stem)
        except ValueError:
            # 非法文件名不属于本模块生成的 session，忽略它而不是让整个列表失败。
            continue
        if session is None or session.metadata is None:
            continue
        if expected_workspace is not None and os.path.normcase(session.workspace) != os.path.normcase(expected_workspace):
            continue
        sessions.append(session.metadata)
    sessions.sort(key=lambda item: item.updated_at, reverse=True)
    return sessions


def get_latest_session(workspace: str | Path | None = None) -> SessionData | None:
    """返回指定工作区最近更新的完整 session，没有记录时返回 None。"""

    sessions = list_sessions(workspace=workspace)
    return load_session(sessions[0].session_id) if sessions else None


def _format_timestamp(timestamp: float) -> str:
    """把 Unix 时间转换为本地可读时间，展示层不泄漏浮点实现细节。"""

    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def format_session_inspect(session: SessionData) -> str:
    """输出会话身份、规模和工作区摘要，适合快速检查持久化状态。"""

    metadata = session.metadata
    return "\n".join(
        [
            f"Session inspect: {session.session_id}",
            f"Created: {_format_timestamp(session.created_at)}",
            f"Updated: {_format_timestamp(session.updated_at)}",
            f"Workspace: {session.workspace}",
            f"Messages: {len(session.messages)}",
            f"Transcript entries: {len(session.transcript_entries)}",
            f"First user message: {metadata.first_message if metadata else ''}",
        ]
    )


def _format_transcript_entry(entry: dict[str, Any]) -> str:
    """把单个 transcript 事件转成人类可读行，并保留工具成功/失败状态。"""

    kind = str(entry.get("kind", "unknown"))
    body = str(entry.get("body", ""))
    if kind == "assistant_tool_call":
        tool_name = entry.get("toolName", "unknown")
        tool_input = json.dumps(entry.get("input"), ensure_ascii=False, sort_keys=True)
        return f"[assistant_tool_call:{tool_name}] {tool_input}"
    if kind == "tool_result":
        tool_name = entry.get("toolName", "unknown")
        status = "error" if entry.get("isError") else "ok"
        return f"[tool_result:{tool_name}/{status}] {body}"
    return f"[{kind}] {body}"


def format_session_replay(session: SessionData) -> str:
    """按原始顺序格式化整个 turn 时间线，作为阶段 8 的最小 replay。"""

    lines = [f"Session replay: {session.session_id}", f"Workspace: {session.workspace}", ""]
    if not session.transcript_entries:
        lines.append("(empty transcript)")
    else:
        lines.extend(_format_transcript_entry(entry) for entry in session.transcript_entries)
    return "\n".join(lines)
