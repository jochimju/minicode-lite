from __future__ import annotations

from pathlib import Path
from typing import Any

from minicode_lite.tooling import ToolContext, ToolDefinition, ToolResult
from minicode_lite.tools._shared import resolve_for_tool


def _validate(input_data: Any) -> dict[str, str]:
    if input_data is None:
        return {"path": "."}
    if not isinstance(input_data, dict):
        raise ValueError("input must be an object")
    path = input_data.get("path", ".")
    if not isinstance(path, str) or not path:
        raise ValueError("path must be a string")
    return {"path": path}


def _run(input_data: dict[str, str], context: ToolContext) -> ToolResult:
    target, error = resolve_for_tool(context, input_data["path"], "list")
    if error is not None:
        return error
    assert target is not None

    if not target.exists():
        return ToolResult(ok=False, output=f"Path does not exist: {input_data['path']}")
    if target.is_file():
        return ToolResult(ok=True, output=f"file {Path(input_data['path']).name}")

    try:
        entries = sorted(target.iterdir(), key=lambda entry: entry.name.lower())
    except OSError as error:
        return ToolResult(ok=False, output=f"Could not list {input_data['path']}: {error}")

    if not entries:
        return ToolResult(ok=True, output="(empty)")

    lines = [f"{'dir' if entry.is_dir() else 'file'} {entry.name}" for entry in entries]
    return ToolResult(ok=True, output="\n".join(lines))


list_files_tool = ToolDefinition(
    name="list_files",
    description="List files and directories relative to the workspace root.",
    input_schema={
        "type": "object",
        "properties": {"path": {"type": "string"}},
    },
    validator=_validate,
    run=_run,
)
