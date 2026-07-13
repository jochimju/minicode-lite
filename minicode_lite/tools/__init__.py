from __future__ import annotations

from minicode_lite.tooling import ToolRegistry
from minicode_lite.tools.edit_file import edit_file_tool
from minicode_lite.tools.list_files import list_files_tool
from minicode_lite.tools.patch_file import patch_file_tool
from minicode_lite.tools.read_file import read_file_tool
from minicode_lite.tools.write_file import write_file_tool


def create_default_tool_registry() -> ToolRegistry:
    return ToolRegistry(
        [
            list_files_tool,
            read_file_tool,
            write_file_tool,
            edit_file_tool,
            patch_file_tool,
        ]
    )


__all__ = [
    "create_default_tool_registry",
    "edit_file_tool",
    "list_files_tool",
    "patch_file_tool",
    "read_file_tool",
    "write_file_tool",
]
