from __future__ import annotations

from typing import Any

from minicode_lite.tooling import ToolContext, ToolDefinition, ToolResult
from minicode_lite.tools._shared import resolve_for_tool, write_text_file


def _validate(input_data: Any) -> dict[str, str]:
    if not isinstance(input_data, dict):
        raise ValueError("input must be an object")
    path = input_data.get("path")
    content = input_data.get("content")
    if not isinstance(path, str) or not path:
        raise ValueError("path is required")
    if not isinstance(content, str):
        raise ValueError("content must be a string")
    return {"path": path, "content": content}


def _run(input_data: dict[str, str], context: ToolContext) -> ToolResult:
    target, error = resolve_for_tool(context, input_data["path"], "write")
    if error is not None:
        return error
    assert target is not None
    return write_text_file(target, input_data["path"], input_data["content"])


write_file_tool = ToolDefinition(
    name="write_file",
    description="Write a UTF-8 text file relative to the workspace root.",
    input_schema={
        "type": "object",
        "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
        "required": ["path", "content"],
    },
    validator=_validate,
    run=_run,
)
