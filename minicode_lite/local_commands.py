from __future__ import annotations

from pathlib import Path

from minicode_lite.tooling import ToolContext, ToolRegistry


def format_tools(tools: ToolRegistry) -> str:
    return "\n".join(f"{tool.name}: {tool.description}" for tool in tools.list())


def try_handle_local_command(
    user_input: str,
    *,
    tools: ToolRegistry,
    cwd: str | Path,
) -> str | None:
    text = user_input.strip()
    if text == "/tools":
        return format_tools(tools)

    if text.startswith("/read "):
        path = text[len("/read ") :].strip()
        if not path:
            return "Usage: /read <path>"
        result = tools.execute(
            "read_file",
            {"path": path},
            ToolContext(cwd=str(cwd)),
        )
        return result.output

    return None
