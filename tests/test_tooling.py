from __future__ import annotations

from minicode_lite.tooling import ToolContext, ToolDefinition, ToolRegistry, ToolResult


def test_registry_executes_registered_tool() -> None:
    def validate_echo(input_data: object) -> dict[str, str]:
        assert isinstance(input_data, dict)
        return {"text": str(input_data["text"])}

    def run_echo(input_data: dict[str, str], _context: ToolContext) -> ToolResult:
        return ToolResult(ok=True, output=f"echo:{input_data['text']}")

    registry = ToolRegistry(
        [
            ToolDefinition(
                name="echo",
                description="Echo text for tests.",
                input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
                validator=validate_echo,
                run=run_echo,
            )
        ]
    )

    result = registry.execute("echo", {"text": "hello"}, ToolContext(cwd="."))

    assert result == ToolResult(ok=True, output="echo:hello")


def test_registry_returns_error_for_unknown_tool() -> None:
    registry = ToolRegistry([])

    result = registry.execute("missing_tool", {}, ToolContext(cwd="."))

    assert result.ok is False
    assert result.output == "Unknown tool: missing_tool"


def test_registry_converts_validation_error_to_tool_result() -> None:
    def fail_validation(_input_data: object) -> dict[str, str]:
        raise ValueError("text is required")

    def run_echo(input_data: dict[str, str], _context: ToolContext) -> ToolResult:
        return ToolResult(ok=True, output=input_data["text"])

    registry = ToolRegistry(
        [
            ToolDefinition(
                name="echo",
                description="Echo text for tests.",
                input_schema={"type": "object"},
                validator=fail_validation,
                run=run_echo,
            )
        ]
    )

    result = registry.execute("echo", {}, ToolContext(cwd="."))

    assert result.ok is False
    assert result.output == "Input validation error in echo: text is required"


def test_registry_converts_run_error_to_tool_result() -> None:
    def validate_echo(input_data: object) -> object:
        return input_data

    def crash_tool(_input_data: object, _context: ToolContext) -> ToolResult:
        raise RuntimeError("tool exploded")

    registry = ToolRegistry(
        [
            ToolDefinition(
                name="echo",
                description="Echo text for tests.",
                input_schema={"type": "object"},
                validator=validate_echo,
                run=crash_tool,
            )
        ]
    )

    result = registry.execute("echo", {"text": "hello"}, ToolContext(cwd="."))

    assert result.ok is False
    assert result.output == "Tool echo crashed: tool exploded"
