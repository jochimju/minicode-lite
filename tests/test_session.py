from __future__ import annotations

import json

import pytest

from minicode_lite import session as session_module
from minicode_lite.session import (
    FileCheckpoint,
    build_transcript,
    create_file_checkpoint,
    create_new_session,
    format_rewind_preview,
    format_session_checkpoints,
    format_session_inspect,
    format_session_replay,
    get_latest_session,
    list_sessions,
    load_session,
    rewind_session,
    rewind_session_data,
    save_session,
)


@pytest.fixture(autouse=True)
def isolated_sessions(tmp_path, monkeypatch):
    monkeypatch.setattr(session_module, "SESSIONS_DIR", tmp_path / "sessions")


def test_create_new_session_normalizes_workspace(tmp_path):
    session = create_new_session(workspace=tmp_path / "workspace" / "..")

    assert len(session.session_id) == 12
    assert session.workspace == str(tmp_path.resolve())
    assert session.messages == []
    assert session.metadata is not None


def test_save_and_load_session_round_trip(tmp_path):
    session = create_new_session(workspace=tmp_path)
    session.messages = [
        {"role": "user", "content": "读取 demo.txt"},
        {"role": "assistant", "content": "完成"},
    ]

    path = save_session(session)
    loaded = load_session(session.session_id)

    assert path.is_file()
    assert loaded is not None
    assert loaded.messages == session.messages
    assert loaded.transcript_entries == session.transcript_entries
    assert loaded.metadata is not None
    assert loaded.metadata.first_message == "读取 demo.txt"


def test_saved_json_is_full_readable_snapshot(tmp_path):
    session = create_new_session(workspace=tmp_path)
    session.messages = [{"role": "user", "content": "hello"}]

    path = save_session(session)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == 1
    assert payload["messages"] == session.messages
    assert payload["transcript_entries"] == session.transcript_entries


def test_list_sessions_filters_workspace(tmp_path):
    first = create_new_session(workspace=tmp_path / "first")
    first.messages = [{"role": "user", "content": "first"}]
    save_session(first)
    second = create_new_session(workspace=tmp_path / "second")
    second.messages = [{"role": "user", "content": "second"}]
    save_session(second)

    assert [item.session_id for item in list_sessions(workspace=tmp_path / "first")] == [first.session_id]
    assert {item.session_id for item in list_sessions()} == {first.session_id, second.session_id}


def test_get_latest_session_uses_updated_time(tmp_path, monkeypatch):
    times = iter([100.0, 101.0, 102.0, 200.0, 201.0, 202.0])
    monkeypatch.setattr(session_module.time, "time", lambda: next(times))
    older = create_new_session(workspace=tmp_path)
    save_session(older)
    newer = create_new_session(workspace=tmp_path)
    save_session(newer)

    latest = get_latest_session(workspace=tmp_path)

    assert latest is not None
    assert latest.session_id == newer.session_id


def test_build_transcript_preserves_tool_pair_and_omits_system():
    transcript = build_transcript(
        [
            {"role": "system", "content": "rules"},
            {"role": "user", "content": "read"},
            {
                "role": "assistant_tool_call",
                "content": "",
                "toolUseId": "call-1",
                "toolName": "read_file",
                "input": {"path": "demo.txt"},
            },
            {
                "role": "tool_result",
                "content": "hello",
                "toolUseId": "call-1",
                "toolName": "read_file",
                "isError": False,
            },
            {"role": "assistant", "content": "done"},
        ]
    )

    assert [entry["kind"] for entry in transcript] == [
        "user",
        "assistant_tool_call",
        "tool_result",
        "assistant",
    ]
    assert transcript[1]["toolUseId"] == transcript[2]["toolUseId"] == "call-1"


def test_format_inspect_and_replay_include_core_events(tmp_path):
    session = create_new_session(workspace=tmp_path)
    session.messages = [
        {"role": "user", "content": "inspect"},
        {
            "role": "tool_result",
            "content": "file body",
            "toolUseId": "1",
            "toolName": "read_file",
            "isError": False,
        },
        {"role": "assistant", "content": "finished"},
    ]
    save_session(session)

    inspect_text = format_session_inspect(session)
    replay_text = format_session_replay(session)

    assert "Messages: 3" in inspect_text
    assert "First user message: inspect" in inspect_text
    assert "[user] inspect" in replay_text
    assert "[tool_result:read_file/ok] file body" in replay_text
    assert "[assistant] finished" in replay_text


def test_load_and_list_skip_corrupt_session():
    session_module.SESSIONS_DIR.mkdir(parents=True)
    (session_module.SESSIONS_DIR / "broken.json").write_text("{", encoding="utf-8")
    (session_module.SESSIONS_DIR / "invalid.name.json").write_text("{}", encoding="utf-8")

    assert load_session("broken") is None
    assert list_sessions() == []


def test_load_rejects_path_traversal_id():
    with pytest.raises(ValueError, match="invalid session id"):
        load_session("../outside")


def test_checkpoint_round_trip_updates_metadata_count(tmp_path):
    target = tmp_path / "demo.txt"
    target.write_text("before\n", encoding="utf-8")
    session = create_new_session(workspace=tmp_path)

    checkpoint = create_file_checkpoint(
        session,
        file_path=target,
        existed=True,
        previous_content="before\n",
    )
    loaded = load_session(session.session_id)

    assert checkpoint is not None
    assert loaded is not None
    assert loaded.checkpoints == [checkpoint]
    assert loaded.metadata is not None
    assert loaded.metadata.checkpoint_count == 1
    assert "Checkpoints: 1" in format_session_inspect(loaded)


def test_rewind_new_file_deletes_it_and_can_undo_rewind(tmp_path):
    target = tmp_path / "created.txt"
    session = create_new_session(workspace=tmp_path)
    create_file_checkpoint(
        session,
        file_path=target,
        existed=False,
        previous_content="",
    )
    target.write_text("created later\n", encoding="utf-8")

    restored = rewind_session_data(session)

    assert len(restored) == 1
    assert target.exists() is False
    assert len(session.checkpoints) == 1
    assert session.checkpoints[0].kind == "rewind"

    rewind_session_data(session)

    assert target.read_text(encoding="utf-8") == "created later\n"


def test_multiple_edit_checkpoints_rewind_by_steps(tmp_path):
    target = tmp_path / "demo.txt"
    target.write_text("zero", encoding="utf-8")
    session = create_new_session(workspace=tmp_path)
    create_file_checkpoint(session, file_path=target, existed=True, previous_content="zero")
    target.write_text("one", encoding="utf-8")
    create_file_checkpoint(session, file_path=target, existed=True, previous_content="one")
    target.write_text("two", encoding="utf-8")

    restored = rewind_session_data(session, steps=2)

    assert len(restored) == 2
    assert target.read_text(encoding="utf-8") == "zero"
    assert session.metadata is not None
    assert session.metadata.checkpoint_count == 1


def test_rewind_preview_and_checkpoint_format_do_not_modify_disk(tmp_path):
    target = tmp_path / "demo.txt"
    target.write_text("current", encoding="utf-8")
    session = create_new_session(workspace=tmp_path)
    checkpoint = FileCheckpoint(
        checkpoint_id="checkpoint01",
        created_at=1.0,
        file_path=str(target),
        existed=True,
        previous_content="old",
    )
    session.checkpoints.append(checkpoint)

    preview = format_rewind_preview(session, checkpoint_id=checkpoint.checkpoint_id)
    listing = format_session_checkpoints(session)

    assert "Would restore 1 checkpoint(s)" in preview
    assert "restore pre-edit state" in preview
    assert checkpoint.checkpoint_id in listing
    assert "Total: 1 checkpoint(s)" in listing
    assert target.read_text(encoding="utf-8") == "current"


def test_rewind_saved_session_restores_existing_file(tmp_path):
    target = tmp_path / "demo.txt"
    target.write_text("before", encoding="utf-8")
    session = create_new_session(workspace=tmp_path)
    checkpoint = create_file_checkpoint(
        session,
        file_path=target,
        existed=True,
        previous_content="before",
    )
    assert checkpoint is not None
    target.write_text("after", encoding="utf-8")

    loaded, restored = rewind_session(session.session_id, checkpoint_id=checkpoint.checkpoint_id)

    assert loaded is not None
    assert len(restored) == 1
    assert target.read_text(encoding="utf-8") == "before"
    persisted = load_session(session.session_id)
    assert persisted is not None
    assert persisted.metadata is not None
    assert persisted.metadata.checkpoint_count == 1


def test_rewind_rejects_checkpoint_outside_session_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("safe", encoding="utf-8")
    session = create_new_session(workspace=workspace)
    session.checkpoints.append(
        FileCheckpoint(
            checkpoint_id="outside00001",
            created_at=1.0,
            file_path=str(outside),
            existed=True,
            previous_content="tampered",
        )
    )

    with pytest.raises(ValueError, match="escapes session workspace"):
        rewind_session_data(session)

    assert outside.read_text(encoding="utf-8") == "safe"


def test_rewind_preflight_rejects_directory_before_restoring_any_file(tmp_path):
    first = tmp_path / "first.txt"
    first.write_text("current", encoding="utf-8")
    directory = tmp_path / "not-a-file"
    directory.mkdir()
    session = create_new_session(workspace=tmp_path)
    session.checkpoints.extend(
        [
            FileCheckpoint("first0000001", 1.0, str(first), True, "old"),
            FileCheckpoint("second000001", 2.0, str(directory), False, ""),
        ]
    )

    with pytest.raises(OSError, match="not a file"):
        rewind_session_data(session, steps=2)

    assert first.read_text(encoding="utf-8") == "current"


def test_rewind_does_not_confuse_duplicate_persisted_checkpoint_ids(tmp_path):
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("first-current", encoding="utf-8")
    second.write_text("second-current", encoding="utf-8")
    session = create_new_session(workspace=tmp_path)
    session.checkpoints.extend(
        [
            FileCheckpoint("duplicate001", 1.0, str(first), True, "first-old"),
            FileCheckpoint("duplicate001", 2.0, str(second), True, "second-old"),
        ]
    )

    rewind_session_data(session, steps=2)

    assert first.read_text(encoding="utf-8") == "first-old"
    assert second.read_text(encoding="utf-8") == "second-old"
