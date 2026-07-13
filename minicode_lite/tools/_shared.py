from __future__ import annotations

from pathlib import Path

from minicode_lite.tooling import ToolContext, ToolResult
from minicode_lite.workspace import resolve_tool_path


def resolve_for_tool(context: ToolContext, path: str, mode: str) -> tuple[Path | None, ToolResult | None]:
    try:
        return resolve_tool_path(context, path, mode), None
    except PermissionError as error:
        return None, ToolResult(ok=False, output=str(error))


def read_text_file(target: Path, display_path: str) -> tuple[str | None, ToolResult | None]:
    try:
        content = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, ToolResult(ok=False, output=f"File not found: {display_path}")
    except IsADirectoryError:
        return None, ToolResult(ok=False, output=f"Path is a directory: {display_path}")
    except UnicodeDecodeError:
        return None, ToolResult(
            ok=False,
            output=f"File {display_path} appears to be binary. Cannot read as UTF-8 text.",
        )
    except OSError as error:
        return None, ToolResult(ok=False, output=f"Could not read {display_path}: {error}")

    if "\x00" in content:
        return None, ToolResult(
            ok=False,
            output=f"File {display_path} appears to be binary. Cannot read as UTF-8 text.",
        )
    return content, None


def write_text_file(target: Path, display_path: str, content: str) -> ToolResult:
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except OSError as error:
        return ToolResult(ok=False, output=f"Could not write {display_path}: {error}")
    return ToolResult(ok=True, output=f"Wrote {display_path}")
