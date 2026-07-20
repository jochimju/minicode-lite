from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from minicode_lite import session as session_module
from minicode_lite.agent_loop import run_agent_turn
from minicode_lite.headless import run_headless
from minicode_lite.mock_model import ScriptedModel
from minicode_lite.permissions import PermissionManager
from minicode_lite.session import (
    create_new_session,
    format_session_replay,
    get_latest_session,
    rewind_session_data,
    save_session,
)
from minicode_lite.tools import create_default_tool_registry
from minicode_lite.types import AgentStep


@pytest.fixture(autouse=True)
def isolated_offline_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINI_CODE_MODEL", "")
    monkeypatch.setenv("CUSTOM_API_BASE_URL", "")
    monkeypatch.setenv("CUSTOM_API_KEY", "")
    monkeypatch.setattr(session_module, "SESSIONS_DIR", tmp_path / "sessions")


def test_prompt_tool_final_session_and_replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "demo.txt").write_text("integration evidence\n", encoding="utf-8")
    model = ScriptedModel(
        [
            AgentStep(
                type="tool_calls",
                calls=[
                    {
                        "id": "integration-read-1",
                        "toolName": "read_file",
                        "input": {"path": "demo.txt"},
                    }
                ],
            ),
            AgentStep(type="assistant", content="The file contains integration evidence."),
        ]
    )
    monkeypatch.setattr(
        "minicode_lite.headless.create_model_adapter",
        lambda _config, _tools: (model, "integration scripted model"),
    )

    answer = run_headless("Read demo.txt and summarize it.", cwd=workspace)
    saved = get_latest_session(workspace=workspace)

    assert answer == "The file contains integration evidence."
    assert saved is not None
    assert saved.messages[3]["role"] == "tool_result"
    assert saved.messages[3]["content"] == "integration evidence\n"
    replay = format_session_replay(saved)
    assert "[tool_result:read_file/ok] integration evidence" in replay
    assert "[assistant] The file contains integration evidence." in replay


def test_write_checkpoint_then_rewind_restores_original_file(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "demo.txt"
    target.write_text("before\n", encoding="utf-8")
    session = create_new_session(workspace)
    model = ScriptedModel(
        [
            AgentStep(
                type="tool_calls",
                calls=[
                    {
                        "id": "integration-write-1",
                        "toolName": "write_file",
                        "input": {"path": "demo.txt", "content": "after\n"},
                    }
                ],
            ),
            AgentStep(type="assistant", content="The write was verified."),
        ]
    )
    permissions = PermissionManager(workspace, prompt_handler=lambda _request: "allow_once")

    messages = run_agent_turn(
        model=model,
        tools=create_default_tool_registry(),
        messages=[{"role": "user", "content": "Replace demo.txt."}],
        cwd=str(workspace),
        permissions=permissions,
        session=session,
    )
    session.messages = messages
    save_session(session)

    assert target.read_text(encoding="utf-8") == "after\n"
    assert len(session.checkpoints) == 1
    restored = rewind_session_data(session)
    assert len(restored) == 1
    assert target.read_text(encoding="utf-8") == "before\n"


def test_readiness_is_machine_readable_in_integration_path(tmp_path: Path) -> None:
    payload = json.loads(run_headless("/readiness --json", cwd=tmp_path))

    assert payload["schema_version"] == "1.0"
    assert payload["status"] == "warning"
    assert payload["mode"] == "mock"
    assert {check["name"] for check in payload["checks"]} == {"python", "cwd", "tools", "model"}


@pytest.mark.skipif(os.name != "nt", reason="Windows path semantics only")
def test_windows_backslash_path_flows_through_tool_and_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    nested = workspace / "nested"
    nested.mkdir(parents=True)
    (nested / "demo.txt").write_text("windows path evidence", encoding="utf-8")
    model = ScriptedModel(
        [
            AgentStep(
                type="tool_calls",
                calls=[
                    {
                        "id": "windows-read-1",
                        "toolName": "read_file",
                        "input": {"path": r"nested\demo.txt"},
                    }
                ],
            ),
            AgentStep(type="assistant", content="Windows path read succeeded."),
        ]
    )
    monkeypatch.setattr(
        "minicode_lite.headless.create_model_adapter",
        lambda _config, _tools: (model, "integration scripted model"),
    )

    assert run_headless("Read the nested Windows path.", cwd=workspace) == "Windows path read succeeded."
    saved = get_latest_session(workspace=workspace)
    assert saved is not None
    assert saved.messages[2]["input"]["path"] == r"nested\demo.txt"
    assert saved.messages[3]["content"] == "windows path evidence"
