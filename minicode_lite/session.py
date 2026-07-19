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
    checkpoint_count: int = 0


@dataclass(slots=True)
class FileCheckpoint:
    """文件工具写盘前留下的持久快照，供 preview 和 rewind 使用。"""

    checkpoint_id: str
    created_at: float
    file_path: str
    existed: bool
    previous_content: str
    # edit 表示普通写前快照，rewind 表示回退前的反向安全快照。
    kind: str = "edit"
    # 同一次 rewind 涉及的多个文件共享 group_id，下一次回退会把它们视为一个整体。
    group_id: str = ""


@dataclass(slots=True)
class SessionData:
    """一份可持久化会话的完整状态：原始消息、可读 transcript 和摘要。"""

    session_id: str
    created_at: float
    updated_at: float
    workspace: str
    messages: list[ChatMessage] = field(default_factory=list)
    transcript_entries: list[dict[str, Any]] = field(default_factory=list)
    checkpoints: list[FileCheckpoint] = field(default_factory=list)
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
            checkpoint_count=len(self.checkpoints),
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
        "checkpoints": [asdict(checkpoint) for checkpoint in session.checkpoints],
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
        checkpoint_data = data.get("checkpoints", [])
        if not isinstance(checkpoint_data, list):
            return None
        session = SessionData(
            session_id=data["session_id"],
            created_at=float(data["created_at"]),
            updated_at=float(data["updated_at"]),
            workspace=str(data["workspace"]),
            messages=_copy_messages(data.get("messages", [])),
            transcript_entries=[dict(entry) for entry in data.get("transcript_entries", [])],
            checkpoints=[FileCheckpoint(**item) for item in checkpoint_data],
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
            f"Checkpoints: {len(session.checkpoints)}",
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


def create_file_checkpoint(
    session: SessionData | None,
    *,
    file_path: str | Path,
    existed: bool,
    previous_content: str,
) -> FileCheckpoint | None:
    """在文件修改前把旧状态追加到 session；无 session 时保持工具可独立使用。"""

    if session is None:
        # 测试或独立工具调用可以没有 session，此时仍执行写入但不承诺可恢复。
        return None
    checkpoint = FileCheckpoint(
        checkpoint_id=uuid.uuid4().hex[:12],
        created_at=time.time(),
        # 工具传入的目标已经过 workspace 解析；再次 resolve 固化稳定绝对路径。
        file_path=str(Path(file_path).resolve()),
        existed=existed,
        previous_content=previous_content,
    )
    session.checkpoints.append(checkpoint)
    # 快照必须先于文件副作用持久化；若保存失败，工具不会继续覆盖磁盘。
    save_session(session)
    return checkpoint


def _select_checkpoints_to_rewind(
    session: SessionData,
    *,
    steps: int = 1,
    checkpoint_id: str | None = None,
) -> list[FileCheckpoint]:
    """选择从目标点到最新的快照；rewind 安全组始终作为不可拆分的一步。"""

    if not session.checkpoints:
        return []
    if checkpoint_id is not None:
        # 从后向前找能在 ID 重复或历史迁移时优先命中最新记录。
        for index in range(len(session.checkpoints) - 1, -1, -1):
            checkpoint = session.checkpoints[index]
            if checkpoint.checkpoint_id != checkpoint_id:
                continue
            if checkpoint.group_id:
                while index > 0 and session.checkpoints[index - 1].group_id == checkpoint.group_id:
                    index -= 1
            return session.checkpoints[index:]
        return []
    if steps <= 0:
        return []
    start_index = max(len(session.checkpoints) - steps, 0)
    # 反向快照可能覆盖多个文件，不能只恢复组内最后一个文件。
    tail_group_id = session.checkpoints[-1].group_id
    if tail_group_id:
        group_start = len(session.checkpoints) - 1
        while group_start > 0 and session.checkpoints[group_start - 1].group_id == tail_group_id:
            group_start -= 1
        start_index = min(start_index, group_start)
    return session.checkpoints[start_index:]


def _validated_rewind_target(session: SessionData, checkpoint: FileCheckpoint) -> Path:
    """重新验证持久化路径，防止被篡改的 session 越过原工作区。"""

    workspace = Path(session.workspace).resolve()
    target = Path(checkpoint.file_path).resolve()
    if target == workspace or workspace not in target.parents:
        raise ValueError(f"checkpoint path escapes session workspace: {checkpoint.file_path}")
    return target


def rewind_session_data(
    session: SessionData,
    *,
    steps: int = 1,
    checkpoint_id: str | None = None,
) -> list[FileCheckpoint]:
    """恢复内存 session 选中的文件快照，并留下可撤销本次回退的安全快照。"""

    selected = _select_checkpoints_to_rewind(
        session,
        steps=steps,
        checkpoint_id=checkpoint_id,
    )
    if not selected:
        return []
    # 在任何磁盘变化前验证整批路径，避免多文件恢复到一半才发现越界记录。
    # 保持与 selected 相同的顺序，不用可被持久化数据篡改成重复值的 checkpoint_id 做映射键。
    targets = [_validated_rewind_target(session, checkpoint) for checkpoint in selected]
    # 当前磁盘对象若已变成目录，不能按文本文件恢复；整批预检保证失败发生在零副作用阶段。
    for target in targets:
        if target.exists() and not target.is_file():
            raise OSError(f"checkpoint target is not a file: {target}")
    rewind_group_id = uuid.uuid4().hex[:12]
    rewind_created_at = time.time()
    reverse_checkpoints: list[FileCheckpoint] = []
    captured_paths: set[str] = set()
    # 同一文件可能被连续编辑多次；反向快照只需保存 rewind 开始时的最终状态一次。
    for checkpoint, target in zip(reversed(selected), reversed(targets), strict=True):
        normalized_path = str(target)
        if normalized_path in captured_paths:
            continue
        existed = target.is_file()
        previous_content = target.read_text(encoding="utf-8") if existed else ""
        reverse_checkpoints.append(
            FileCheckpoint(
                checkpoint_id=uuid.uuid4().hex[:12],
                created_at=rewind_created_at,
                file_path=normalized_path,
                existed=existed,
                previous_content=previous_content,
                kind="rewind",
                group_id=rewind_group_id,
            )
        )
        captured_paths.add(normalized_path)
    # 倒序应用才能把“第一次前 -> 第二次前”正确还原到最早选中的状态。
    for checkpoint, target in zip(reversed(selected), reversed(targets), strict=True):
        if checkpoint.existed:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(checkpoint.previous_content, encoding="utf-8")
        elif target.exists():
            target.unlink()
    del session.checkpoints[-len(selected) :]
    session.checkpoints.extend(reverse_checkpoints)
    save_session(session)
    return selected


def rewind_session(
    session_id: str,
    *,
    steps: int = 1,
    checkpoint_id: str | None = None,
) -> tuple[SessionData | None, list[FileCheckpoint]]:
    """加载指定 session 并执行 rewind；不存在时返回空结果而不是触碰磁盘。"""

    session = load_session(session_id)
    if session is None:
        return None, []
    restored = rewind_session_data(session, steps=steps, checkpoint_id=checkpoint_id)
    return session, restored


def format_rewind_preview(
    session: SessionData,
    *,
    steps: int = 1,
    checkpoint_id: str | None = None,
) -> str:
    """只展示计划恢复的快照，不读取或修改当前文件内容。"""

    selected = _select_checkpoints_to_rewind(
        session,
        steps=steps,
        checkpoint_id=checkpoint_id,
    )
    if not selected:
        return f"No checkpoints available to rewind for session {session.session_id}."
    unique_files = list(dict.fromkeys(checkpoint.file_path for checkpoint in reversed(selected)))
    lines = [
        f"Rewind preview for session {session.session_id}:",
        f"Would restore {len(selected)} checkpoint(s) across {len(unique_files)} file(s).",
    ]
    if checkpoint_id is not None:
        lines.append(f"Target checkpoint: {checkpoint_id}")
    mode = "undo prior rewind" if any(item.kind == "rewind" for item in selected) else "restore pre-edit state"
    lines.append(f"Mode: {mode}.")
    for checkpoint in reversed(selected):
        state = "existing file" if checkpoint.existed else "new file"
        lines.append(f"- [{checkpoint.checkpoint_id}] {checkpoint.file_path} -> {state}")
    return "\n".join(lines)


def format_session_checkpoints(session: SessionData) -> str:
    """按从新到旧的顺序展示 session 当前可用恢复点。"""

    if not session.checkpoints:
        return f"No checkpoints saved for session {session.session_id}."
    lines = [f"Session checkpoints: {session.session_id}"]
    for checkpoint in reversed(session.checkpoints):
        state = "existing file" if checkpoint.existed else "new file"
        lines.append(
            f"- [{checkpoint.checkpoint_id}] {checkpoint.kind}: {checkpoint.file_path} ({state})"
        )
    lines.append(f"Total: {len(session.checkpoints)} checkpoint(s)")
    return "\n".join(lines)
