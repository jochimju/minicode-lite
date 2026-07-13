from __future__ import annotations

from pathlib import Path

import pytest

from minicode_lite.headless import run_headless


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
