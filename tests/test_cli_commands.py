from __future__ import annotations

from pathlib import Path

import minicode_lite.session as session_module
from minicode_lite.cli_commands import (
    format_memory_status,
    format_session_list,
    format_tools,
    try_handle_local_command,
)
from minicode_lite.memory import MemoryManager
from minicode_lite.session import create_file_checkpoint, create_new_session, save_session
from minicode_lite.tooling import ToolRegistry
from minicode_lite.tools import create_default_tool_registry


def _handle(command: str, workspace: Path, *, session=None) -> str | None:
    return try_handle_local_command(
        command,
        tools=create_default_tool_registry(),
        cwd=workspace,
        session=session,
    )


def _saved_session(workspace: Path, first_message: str = "inspect project"):
    session = create_new_session(workspace)
    session.messages = [
        {"role": "user", "content": first_message},
        {"role": "assistant", "content": "done"},
    ]
    save_session(session)
    return session


def test_format_tools_lists_registered_definitions_and_handles_empty_registry() -> None:
    output = format_tools(create_default_tool_registry())

    assert output.splitlines()[0].startswith("list_files:")
    assert "run_command:" in output
    assert format_tools(ToolRegistry([])) == "No tools registered."


def test_sessions_command_lists_only_current_workspace(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(session_module, "SESSIONS_DIR", tmp_path / "sessions")
    current = tmp_path / "current"
    other = tmp_path / "other"
    current.mkdir()
    other.mkdir()
    current_session = _saved_session(current, "current task")
    _saved_session(other, "other task")

    output = _handle("/sessions", current)

    assert output is not None
    assert current_session.session_id in output
    assert "current task" in output
    assert "other task" not in output
    assert "Total: 1 session(s)" in output


def test_session_command_uses_active_then_latest_saved_session(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(session_module, "SESSIONS_DIR", tmp_path / "sessions")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    saved = _saved_session(workspace)

    latest_output = _handle("/session", workspace)
    active = create_new_session(workspace)
    active.messages = [{"role": "user", "content": "live task"}]
    active_output = _handle("/session", workspace, session=active)

    assert latest_output is not None and f"Session inspect: {saved.session_id}" in latest_output
    assert active_output is not None and f"Session inspect: {active.session_id}" in active_output


def test_session_command_ignores_active_session_from_another_workspace(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(session_module, "SESSIONS_DIR", tmp_path / "sessions")
    workspace = tmp_path / "workspace"
    other = tmp_path / "other"
    workspace.mkdir()
    other.mkdir()
    foreign_active = create_new_session(other)

    output = _handle("/session", workspace, session=foreign_active)

    assert output == "No saved session found for this workspace."


def test_session_replay_command_formats_saved_transcript(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(session_module, "SESSIONS_DIR", tmp_path / "sessions")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    saved = _saved_session(workspace, "replay me")

    output = _handle(f"/session-replay {saved.session_id}", workspace)

    assert output is not None
    assert f"Session replay: {saved.session_id}" in output
    assert "[user] replay me" in output
    assert "[assistant] done" in output


def test_checkpoints_command_shows_saved_checkpoint(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(session_module, "SESSIONS_DIR", tmp_path / "sessions")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "demo.txt"
    target.write_text("before", encoding="utf-8")
    session = _saved_session(workspace)
    checkpoint = create_file_checkpoint(
        session,
        file_path=target,
        existed=True,
        previous_content="before",
    )

    output = _handle("/checkpoints", workspace)

    assert checkpoint is not None and output is not None
    assert checkpoint.checkpoint_id in output
    assert str(target.resolve()) in output


def test_rewind_preview_does_not_change_file_or_session(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(session_module, "SESSIONS_DIR", tmp_path / "sessions")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "demo.txt"
    target.write_text("before", encoding="utf-8")
    session = _saved_session(workspace)
    create_file_checkpoint(session, file_path=target, existed=True, previous_content="before")
    target.write_text("after", encoding="utf-8")
    checkpoint_ids = [item.checkpoint_id for item in session.checkpoints]

    output = _handle("/rewind-preview", workspace, session=session)

    assert output is not None and "Would restore 1 checkpoint(s)" in output
    assert target.read_text(encoding="utf-8") == "after"
    assert [item.checkpoint_id for item in session.checkpoints] == checkpoint_ids


def test_rewind_command_restores_file_and_reports_reverse_checkpoint(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(session_module, "SESSIONS_DIR", tmp_path / "sessions")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "demo.txt"
    target.write_text("before", encoding="utf-8")
    session = _saved_session(workspace)
    create_file_checkpoint(session, file_path=target, existed=True, previous_content="before")
    target.write_text("after", encoding="utf-8")

    output = _handle("/rewind", workspace, session=session)

    assert output is not None and "Rewound 1 checkpoint(s)" in output
    assert "reverse checkpoint was saved" in output
    assert target.read_text(encoding="utf-8") == "before"
    assert len(session.checkpoints) == 1
    assert session.checkpoints[0].kind == "rewind"


def test_memory_command_shows_workspace_storage_and_entry_count(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    memory = MemoryManager(workspace)
    assert "Entries: 0" in format_memory_status(memory)
    memory.add("Use pytest for verification")

    output = _handle("/memory", workspace)

    assert output is not None
    assert f"Workspace: {workspace.resolve()}" in output
    assert "memory.json (present)" in output
    assert "Entries: 1" in output


def test_commands_without_session_return_friendly_message(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(session_module, "SESSIONS_DIR", tmp_path / "sessions")
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    for command in ["/session", "/session-replay", "/checkpoints", "/rewind-preview", "/rewind"]:
        assert _handle(command, workspace) == "No saved session found for this workspace."
    assert _handle("/sessions", workspace) == "No saved sessions found for this workspace."


def test_invalid_arguments_are_local_and_unknown_input_returns_none(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    assert _handle("/rewind 0", workspace) == "Usage: /rewind [latest|steps|checkpoint-id]"
    assert _handle("/session too many", workspace) == "Usage: /session [session-id|latest]"
    assert _handle("/tools extra", workspace) == "Usage: /tools"
    assert _handle("/sessions extra", workspace) == "Usage: /sessions"
    assert _handle("/memory extra", workspace) == "Usage: /memory"
    assert _handle("explain the project", workspace) is None
    assert _handle("/unknown", workspace) is None


def test_format_session_list_handles_empty_input() -> None:
    assert format_session_list([]) == "No saved sessions found for this workspace."
