from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from minicode_lite import session as session_module
from minicode_lite.config import RuntimeConfig
from minicode_lite.headless import run, run_headless
from minicode_lite.mock_model import ScriptedModel
from minicode_lite.memory import MemoryManager
from minicode_lite.permissions import PermissionManager
from minicode_lite.prompt import build_system_prompt
from minicode_lite.types import AgentStep


@pytest.fixture(autouse=True)
def _force_mock_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """隔离本机 .env，确保 headless 单元测试始终覆盖 mock 契约。"""

    # 环境变量优先级最高；显式置空可覆盖本机真实凭据，防止离线测试意外触网。
    monkeypatch.setenv("MINI_CODE_MODEL", "")
    monkeypatch.setenv("CUSTOM_API_BASE_URL", "")
    monkeypatch.setenv("CUSTOM_API_KEY", "")
    # 每个测试使用隔离目录，避免 headless 自动保存把真实 session 写进用户目录。
    monkeypatch.setattr(session_module, "SESSIONS_DIR", tmp_path / "sessions")


def test_run_headless_rejects_empty_prompt(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="empty prompt"):
        run_headless("", cwd=tmp_path)


def test_run_headless_returns_mock_assistant_response(tmp_path: Path) -> None:
    response = run_headless("hello", cwd=tmp_path)

    assert response == "MiniCode Lite mock model received your message."


def test_run_headless_read_slash_command_reads_workspace_file(tmp_path: Path) -> None:
    (tmp_path / "demo.txt").write_text("hello from file\n", encoding="utf-8")

    response = run_headless("/read demo.txt", cwd=tmp_path)

    assert "hello from file" in response


def test_run_headless_passes_system_prompt_before_user_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = ScriptedModel([AgentStep(type="assistant", content="configured response")])
    captured: dict[str, object] = {}

    def fake_create_model_adapter(config: RuntimeConfig, tools: object) -> tuple[ScriptedModel, str]:
        captured["config"] = config
        captured["tools"] = tools
        return model, "test registry diagnostic"

    monkeypatch.setattr("minicode_lite.headless.create_model_adapter", fake_create_model_adapter)

    response = run_headless("explain the workspace", cwd=tmp_path)

    assert response == "configured response"
    assert model.received_messages == [
        [
            {
                "role": "system",
                    "content": build_system_prompt(
                        cwd=str(tmp_path),
                        tools=captured["tools"],
                        permissions=PermissionManager(tmp_path),
                        memory_context=MemoryManager(tmp_path).get_context("explain the workspace"),
                    ),
            },
            {"role": "user", "content": "explain the workspace"},
        ]
    ]


def test_run_headless_injects_relevant_project_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    MemoryManager(tmp_path).add("文件编辑前必须创建 checkpoint。", tags=["安全"])
    model = ScriptedModel([AgentStep(type="assistant", content="memory used")])
    monkeypatch.setattr(
        "minicode_lite.headless.create_model_adapter",
        lambda _config, _tools: (model, "test"),
    )

    result = run_headless("修改文件时要遵守什么 checkpoint 规则？", cwd=tmp_path)

    assert result == "memory used"
    system_prompt = model.received_messages[0][0]["content"]
    assert "Memory:\n- 文件编辑前必须创建 checkpoint。" in system_prompt


def test_run_headless_persists_messages_and_transcript(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = ScriptedModel(
        [
            AgentStep(
                type="tool_calls",
                calls=[
                    {
                        "id": "call-1",
                        "toolName": "read_file",
                        "input": {"path": "demo.txt"},
                    }
                ],
            ),
            AgentStep(type="assistant", content="saved response", kind="final"),
        ]
    )
    (tmp_path / "demo.txt").write_text("session body", encoding="utf-8")
    monkeypatch.setattr(
        "minicode_lite.headless.create_model_adapter",
        lambda _config, _tools: (model, "test"),
    )

    result = run_headless("read demo.txt", cwd=tmp_path)
    saved = session_module.get_latest_session(workspace=tmp_path)

    assert result == "saved response"
    assert saved is not None
    assert [message["role"] for message in saved.messages] == [
        "system",
        "user",
        "assistant_tool_call",
        "tool_result",
        "assistant",
    ]
    assert [entry["kind"] for entry in saved.transcript_entries] == [
        "user",
        "assistant_tool_call",
        "tool_result",
        "assistant",
    ]


def test_run_headless_handles_local_command_before_loading_config_or_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "minicode_lite.headless.load_runtime_config",
        lambda: pytest.fail("local commands must not load runtime configuration"),
    )
    monkeypatch.setattr(
        "minicode_lite.headless.create_model_adapter",
        lambda *_args: pytest.fail("local commands must not create a model"),
    )

    response = run_headless("/tools", cwd=tmp_path)

    assert "read_file" in response


def test_run_headless_memory_command_does_not_load_runtime_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "minicode_lite.headless.load_runtime_config",
        lambda: pytest.fail("local commands must not load runtime configuration"),
    )

    response = run_headless("/memory", cwd=tmp_path)

    assert "Project memory:" in response
    assert "Entries: 0" in response


def test_run_headless_readiness_json_uses_mock_fallback_without_creating_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "minicode_lite.headless.create_model_adapter",
        lambda *_args: pytest.fail("readiness must not create a model"),
    )

    payload = json.loads(run_headless("/readiness --json", cwd=tmp_path))

    assert payload["status"] == "warning"
    assert payload["mode"] == "mock"
    assert next(check for check in payload["checks"] if check["name"] == "tools")["status"] == "pass"


def test_headless_cli_reports_runtime_error_without_traceback(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_provider(_prompt: str) -> str:
        raise RuntimeError("Bearer stage6-secret-token")

    monkeypatch.setattr("minicode_lite.headless.run_headless", fail_provider)
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = run(["hello"], stdout=stdout, stderr=stderr)

    assert exit_code == 1
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == "Error: model provider request failed\n"
    assert "stage6-secret-token" not in stderr.getvalue()
    assert "Traceback" not in stderr.getvalue()


def test_headless_cli_preserves_value_error_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject_prompt(_prompt: str) -> str:
        raise ValueError("empty prompt")

    monkeypatch.setattr("minicode_lite.headless.run_headless", reject_prompt)
    stderr = io.StringIO()

    exit_code = run(["hello"], stderr=stderr)

    assert exit_code == 1
    assert stderr.getvalue() == "Error: empty prompt\n"


def test_headless_cli_routes_readiness_json_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[str] = []
    monkeypatch.setattr(
        "minicode_lite.headless.run_headless",
        lambda prompt: captured.append(prompt) or '{"status": "warning"}',
    )
    stdout = io.StringIO()

    exit_code = run(["/readiness", "--json"], stdout=stdout)

    assert exit_code == 0
    assert captured == ["/readiness --json"]
    assert json.loads(stdout.getvalue())["status"] == "warning"


def test_headless_cli_rejects_json_for_other_prompts() -> None:
    stderr = io.StringIO()

    exit_code = run(["hello", "--json"], stderr=stderr)

    assert exit_code == 1
    assert stderr.getvalue() == "Error: --json is only valid with /readiness\n"
