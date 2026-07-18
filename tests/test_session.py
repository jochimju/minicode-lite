from __future__ import annotations

import json

import pytest

from minicode_lite import session as session_module
from minicode_lite.session import (
    build_transcript,
    create_new_session,
    format_session_inspect,
    format_session_replay,
    get_latest_session,
    list_sessions,
    load_session,
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
