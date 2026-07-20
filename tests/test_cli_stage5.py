from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

from minicode_lite.main import run


@pytest.fixture(autouse=True)
def _force_mock_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    """让 CLI 离线测试不受开发者本机真实模型配置影响。"""

    # 测试目标是 Stage 5 的 mock CLI 行为，置空高优先级字段可阻止 .env 触发网络调用。
    monkeypatch.setenv("MINI_CODE_MODEL", "")
    monkeypatch.setenv("CUSTOM_API_BASE_URL", "")
    monkeypatch.setenv("CUSTOM_API_KEY", "")


def test_cli_prompt_runs_headless_turn(tmp_path: Path) -> None:
    stdout = io.StringIO()

    exit_code = run(["hello"], stdout=stdout, cwd=tmp_path)

    assert exit_code == 0
    assert stdout.getvalue().strip() == "MiniCode Lite mock model received your message."


def test_cli_tools_command_lists_default_tools(tmp_path: Path) -> None:
    stdout = io.StringIO()

    exit_code = run(["/tools"], stdout=stdout, cwd=tmp_path)

    assert exit_code == 0
    output = stdout.getvalue()
    assert "read_file:" in output
    assert "list_files:" in output


def test_cli_read_command_reads_workspace_file(tmp_path: Path) -> None:
    (tmp_path / "demo.txt").write_text("stage five\n", encoding="utf-8")
    stdout = io.StringIO()

    exit_code = run(["/read", "demo.txt"], stdout=stdout, cwd=tmp_path)

    assert exit_code == 0
    assert stdout.getvalue().strip() == "stage five"


def test_module_cli_accepts_prompt(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root)
    completed = subprocess.run(
        [sys.executable, "-m", "minicode_lite", "hello"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stdout.strip() == "MiniCode Lite mock model received your message."


def test_cli_reports_runtime_error_without_traceback(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_provider(_prompt: str, *, cwd: str | Path | None = None) -> str:
        del cwd
        raise RuntimeError("Bearer stage6-secret-token")

    monkeypatch.setattr("minicode_lite.main.run_headless", fail_provider)
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = run(["hello"], stdout=stdout, stderr=stderr)

    assert exit_code == 1
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == "Error: model provider request failed\n"
    assert "stage6-secret-token" not in stderr.getvalue()
    assert "Traceback" not in stderr.getvalue()


def test_cli_preserves_value_error_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject_prompt(_prompt: str, *, cwd: str | Path | None = None) -> str:
        del cwd
        raise ValueError("empty prompt")

    monkeypatch.setattr("minicode_lite.main.run_headless", reject_prompt)
    stderr = io.StringIO()

    exit_code = run(["hello"], stderr=stderr)

    assert exit_code == 1
    assert stderr.getvalue() == "Error: empty prompt\n"


def test_main_cli_routes_readiness_json_flag(tmp_path: Path) -> None:
    stdout = io.StringIO()

    exit_code = run(["/readiness", "--json"], stdout=stdout, cwd=tmp_path)

    assert exit_code == 0
    assert '"schema_version": "1.0"' in stdout.getvalue()


def test_main_cli_rejects_json_for_other_prompts() -> None:
    stderr = io.StringIO()

    exit_code = run(["hello", "--json"], stderr=stderr)

    assert exit_code == 1
    assert stderr.getvalue() == "Error: --json is only valid with /readiness\n"
