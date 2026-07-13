from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path

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
