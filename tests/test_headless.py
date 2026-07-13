from __future__ import annotations

import io
from pathlib import Path

import pytest

from minicode_lite.config import RuntimeConfig
from minicode_lite.headless import run, run_headless
from minicode_lite.mock_model import ScriptedModel
from minicode_lite.prompt import build_system_prompt
from minicode_lite.types import AgentStep


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
                "content": build_system_prompt(cwd=str(tmp_path), tools=captured["tools"]),
            },
            {"role": "user", "content": "explain the workspace"},
        ]
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


def test_headless_cli_reports_runtime_error_without_traceback(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_provider(_prompt: str) -> str:
        raise RuntimeError("Qwen-compatible request failed with HTTP status 401.")

    monkeypatch.setattr("minicode_lite.headless.run_headless", fail_provider)
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = run(["hello"], stdout=stdout, stderr=stderr)

    assert exit_code == 1
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == "Error: Qwen-compatible request failed with HTTP status 401.\n"
    assert "Traceback" not in stderr.getvalue()


def test_headless_cli_preserves_value_error_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject_prompt(_prompt: str) -> str:
        raise ValueError("empty prompt")

    monkeypatch.setattr("minicode_lite.headless.run_headless", reject_prompt)
    stderr = io.StringIO()

    exit_code = run(["hello"], stderr=stderr)

    assert exit_code == 1
    assert stderr.getvalue() == "Error: empty prompt\n"
