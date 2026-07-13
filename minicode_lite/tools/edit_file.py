from __future__ import annotations

from typing import Any

from minicode_lite.tooling import ToolContext, ToolDefinition, ToolResult
from minicode_lite.tools._shared import read_text_file, resolve_for_tool, write_text_file


def _validate(input_data: Any) -> dict[str, Any]:
    if not isinstance(input_data, dict):
        raise ValueError("input must be an object")
    path = input_data.get("path")
    old = input_data.get("old", input_data.get("search"))
    new = input_data.get("new", input_data.get("replace"))
    replace_all = bool(input_data.get("replace_all", input_data.get("replaceAll", False)))

    if not isinstance(path, str) or not path:
        raise ValueError("path is required")
    if not isinstance(old, str) or not old:
        raise ValueError("old must be a non-empty string")
    if not isinstance(new, str):
        raise ValueError("new must be a string")

    return {
        "path": path,
        "old": old.replace("\r\n", "\n"),
        "new": new.replace("\r\n", "\n"),
        "replace_all": replace_all,
    }


def _run(input_data: dict[str, Any], context: ToolContext) -> ToolResult:
    target, error = resolve_for_tool(context, input_data["path"], "write")
    if error is not None:
        return error
    assert target is not None

    content, read_error = read_text_file(target, input_data["path"])
    if read_error is not None:
        return read_error
    assert content is not None

    replace_all = bool(input_data.get("replace_all", input_data.get("replaceAll", False)))
    matches = content.count(input_data["old"])
    if matches == 0:
        return ToolResult(ok=False, output=f"Text not found in {input_data['path']}")
    if matches > 1 and not replace_all:
        return ToolResult(
            ok=False,
            output=f"Found multiple matches in {input_data['path']}; use replace_all=true.",
        )

    count = -1 if replace_all else 1
    updated = content.replace(input_data["old"], input_data["new"], count)
    result = write_text_file(target, input_data["path"], updated)
    if not result.ok:
        return result
    return ToolResult(ok=True, output=f"Edited {input_data['path']}")


edit_file_tool = ToolDefinition(
    name="edit_file",
    description="Replace exact text in a UTF-8 file relative to the workspace root.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "old": {"type": "string"},
            "new": {"type": "string"},
            "replace_all": {"type": "boolean"},
        },
        "required": ["path", "old", "new"],
    },
    validator=_validate,
    run=_run,
)
