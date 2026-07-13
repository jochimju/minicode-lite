from __future__ import annotations

from typing import Any

from minicode_lite.tooling import ToolContext, ToolDefinition, ToolResult
from minicode_lite.tools._shared import read_text_file, resolve_for_tool, write_text_file


def _validate(input_data: Any) -> dict[str, Any]:
    if not isinstance(input_data, dict):
        raise ValueError("input must be an object")
    path = input_data.get("path")
    replacements = input_data.get("replacements")
    if not isinstance(path, str) or not path:
        raise ValueError("path is required")
    if not isinstance(replacements, list) or not replacements:
        raise ValueError("replacements must be a non-empty list")

    normalized = []
    for replacement in replacements:
        if not isinstance(replacement, dict):
            raise ValueError("replacement entries must be objects")
        old = replacement.get("old", replacement.get("search"))
        new = replacement.get("new", replacement.get("replace"))
        replace_all = bool(replacement.get("replace_all", replacement.get("replaceAll", False)))
        if not isinstance(old, str) or not old:
            raise ValueError("replacement old must be a non-empty string")
        if not isinstance(new, str):
            raise ValueError("replacement new must be a string")
        normalized.append(
            {
                "old": old.replace("\r\n", "\n"),
                "new": new.replace("\r\n", "\n"),
                "replace_all": replace_all,
            }
        )

    return {"path": path, "replacements": normalized}


def _run(input_data: dict[str, Any], context: ToolContext) -> ToolResult:
    target, error = resolve_for_tool(context, input_data["path"], "write")
    if error is not None:
        return error
    assert target is not None

    content, read_error = read_text_file(target, input_data["path"])
    if read_error is not None:
        return read_error
    assert content is not None

    applied = 0
    for index, replacement in enumerate(input_data["replacements"], start=1):
        if replacement["old"] not in content:
            return ToolResult(
                ok=False,
                output=f"Replacement {index} not found in {input_data['path']}",
            )
        replace_all = bool(replacement.get("replace_all", replacement.get("replaceAll", False)))
        count = -1 if replace_all else 1
        content = content.replace(replacement["old"], replacement["new"], count)
        applied += 1

    result = write_text_file(target, input_data["path"], content)
    if not result.ok:
        return result
    return ToolResult(
        ok=True,
        output=f"Patched {input_data['path']} with {applied} replacement(s)",
    )


patch_file_tool = ToolDefinition(
    name="patch_file",
    description="Apply multiple exact-text replacements to a UTF-8 file.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "replacements": {"type": "array"},
        },
        "required": ["path", "replacements"],
    },
    validator=_validate,
    run=_run,
)
