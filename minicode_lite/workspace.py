from __future__ import annotations

from pathlib import Path

from minicode_lite.tooling import ToolContext


def resolve_tool_path(context: ToolContext, path: str, mode: str) -> Path:
    workspace_root = Path(context.cwd).resolve()
    candidate = Path(path)
    target = candidate if candidate.is_absolute() else workspace_root / candidate
    normalized = target.resolve()

    if context.permissions is not None:
        context.permissions.ensure_path_access(str(normalized), mode)
        return normalized

    try:
        normalized.relative_to(workspace_root)
    except ValueError as error:
        raise PermissionError(f"Path escapes workspace: {path}") from error

    return normalized
