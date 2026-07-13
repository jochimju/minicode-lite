from __future__ import annotations

from pathlib import Path

import pytest

from minicode_lite.tooling import ToolContext
from minicode_lite.workspace import resolve_tool_path


def test_resolve_tool_path_allows_workspace_relative_paths(tmp_path: Path) -> None:
    target = resolve_tool_path(ToolContext(cwd=str(tmp_path)), "notes/demo.txt", "read")

    assert target == tmp_path / "notes" / "demo.txt"


def test_resolve_tool_path_rejects_paths_that_escape_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(PermissionError, match="escapes workspace"):
        resolve_tool_path(ToolContext(cwd=str(workspace)), "../outside.txt", "read")


def test_resolve_tool_path_delegates_to_permissions_when_present(tmp_path: Path) -> None:
    calls: list[tuple[str, str]] = []

    class Permissions:
        def ensure_path_access(self, path: str, intent: str) -> None:
            calls.append((path, intent))

    target = resolve_tool_path(
        ToolContext(cwd=str(tmp_path), permissions=Permissions()),
        "demo.txt",
        "write",
    )

    assert target == tmp_path / "demo.txt"
    assert calls == [(str(tmp_path / "demo.txt"), "write")]
