from __future__ import annotations

from typing import Any

from minicode_lite.tooling import ToolContext, ToolDefinition, ToolResult
from minicode_lite.tools._shared import read_text_file, resolve_for_tool


def _validate(input_data: Any) -> dict[str, str]:
    if not isinstance(input_data, dict):
        raise ValueError("input must be an object")
    path = input_data.get("path")
    if not isinstance(path, str) or not path:
        raise ValueError("path is required")
    return {"path": path}


def _run(input_data: dict[str, str], context: ToolContext) -> ToolResult:
    target, error = resolve_for_tool(context, input_data["path"], "read")
    if error is not None:
        return error
    assert target is not None

    content, read_error = read_text_file(target, input_data["path"])
    if read_error is not None:
        return read_error
    assert content is not None
    return ToolResult(ok=True, output=content)


read_file_tool = ToolDefinition(
    name="read_file",
    description="Read a UTF-8 text file relative to the workspace root.",
    input_schema={
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
    validator=_validate,
    run=_run,
)
