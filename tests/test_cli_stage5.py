from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

from minicode_lite.main import run


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
