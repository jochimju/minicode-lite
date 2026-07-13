from __future__ import annotations

from pathlib import Path

from minicode_lite.tooling import ToolContext
from minicode_lite.tools import create_default_tool_registry
from minicode_lite.tools.edit_file import edit_file_tool
from minicode_lite.tools.list_files import list_files_tool
from minicode_lite.tools.patch_file import patch_file_tool
from minicode_lite.tools.read_file import read_file_tool
from minicode_lite.tools.write_file import write_file_tool


def test_read_file_tool_reads_utf8_text(tmp_path: Path) -> None:
    (tmp_path / "demo.txt").write_text("hello\n世界\n", encoding="utf-8")

    result = read_file_tool.run({"path": "demo.txt"}, ToolContext(cwd=str(tmp_path)))

    assert result.ok is True
    assert result.output == "hello\n世界\n"


def test_read_file_tool_reports_binary_files(tmp_path: Path) -> None:
    (tmp_path / "demo.bin").write_bytes(b"\xff\xfe\x00\x00")

    result = read_file_tool.run({"path": "demo.bin"}, ToolContext(cwd=str(tmp_path)))

    assert result.ok is False
    assert "binary" in result.output.lower()


def test_write_file_tool_writes_new_utf8_file(tmp_path: Path) -> None:
    result = write_file_tool.run(
        {"path": "notes/demo.txt", "content": "hello\n"},
        ToolContext(cwd=str(tmp_path)),
    )

    assert result.ok is True
    assert result.output == "Wrote notes/demo.txt"
    assert (tmp_path / "notes" / "demo.txt").read_text(encoding="utf-8") == "hello\n"


def test_edit_file_tool_replaces_one_matching_block(tmp_path: Path) -> None:
    target = tmp_path / "demo.txt"
    target.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")

    result = edit_file_tool.run(
        {"path": "demo.txt", "old": "beta\n", "new": "BETA\n"},
        ToolContext(cwd=str(tmp_path)),
    )

    assert result.ok is True
    assert target.read_text(encoding="utf-8") == "alpha\nBETA\ngamma\n"


def test_edit_file_tool_rejects_ambiguous_replacements(tmp_path: Path) -> None:
    target = tmp_path / "demo.txt"
    target.write_text("same\nsame\n", encoding="utf-8")

    result = edit_file_tool.run(
        {"path": "demo.txt", "old": "same", "new": "changed"},
        ToolContext(cwd=str(tmp_path)),
    )

    assert result.ok is False
    assert "multiple matches" in result.output.lower()
    assert target.read_text(encoding="utf-8") == "same\nsame\n"


def test_patch_file_tool_applies_multiple_replacements(tmp_path: Path) -> None:
    target = tmp_path / "demo.txt"
    target.write_text("hello world\nhello agent\n", encoding="utf-8")

    result = patch_file_tool.run(
        {
            "path": "demo.txt",
            "replacements": [
                {"old": "hello world", "new": "hi world"},
                {"old": "hello agent", "new": "hi agent"},
            ],
        },
        ToolContext(cwd=str(tmp_path)),
    )

    assert result.ok is True
    assert "2 replacement" in result.output
    assert target.read_text(encoding="utf-8") == "hi world\nhi agent\n"


def test_file_tools_reject_paths_that_escape_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    result = read_file_tool.run({"path": "../outside.txt"}, ToolContext(cwd=str(workspace)))

    assert result.ok is False
    assert "escapes workspace" in result.output
    assert outside.read_text(encoding="utf-8") == "secret"


def test_list_files_tool_lists_workspace_entries(tmp_path: Path) -> None:
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    (tmp_path / "a").mkdir()

    result = list_files_tool.run({"path": "."}, ToolContext(cwd=str(tmp_path)))

    assert result.ok is True
    assert result.output.splitlines() == ["dir a", "file b.txt"]


def test_default_tool_registry_contains_stage4_file_tools(tmp_path: Path) -> None:
    registry = create_default_tool_registry()

    names = {tool.name for tool in registry.list()}

    assert names == {"list_files", "read_file", "write_file", "edit_file", "patch_file"}
