from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ToolResult:
    ok: bool
    output: str


@dataclass(slots=True)
class ToolContext:
    cwd: str
    permissions: Any | None = None
    session: Any | None = None
    runtime: dict[str, Any] | None = None


Validator = Callable[[Any], Any]
Runner = Callable[[Any, ToolContext], ToolResult]


@dataclass(slots=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    validator: Validator
    run: Runner


class ToolRegistry:
    def __init__(self, tools: list[ToolDefinition]) -> None:
        self._tools = list(tools)
        self._tool_index = {tool.name: tool for tool in tools}

    def list(self) -> list[ToolDefinition]:
        return list(self._tools)

    def find(self, name: str) -> ToolDefinition | None:
        return self._tool_index.get(name)

    def execute(self, tool_name: str, input_data: Any, context: ToolContext) -> ToolResult:
        tool = self.find(tool_name)
        if tool is None:
            return ToolResult(ok=False, output=f"Unknown tool: {tool_name}")
        try:
            parsed = tool.validator(input_data)
        except (KeyError, TypeError, ValueError) as error:
            return ToolResult(ok=False, output=f"Input validation error in {tool_name}: {error}")
        try:
            return tool.run(parsed, context)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as error:  # noqa: BLE001
            return ToolResult(ok=False, output=f"Tool {tool_name} crashed: {error}")
