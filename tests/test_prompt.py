from __future__ import annotations

from minicode_lite.prompt import build_system_prompt
from minicode_lite.tooling import ToolContext, ToolDefinition, ToolRegistry, ToolResult


def _echo_tool() -> ToolDefinition:
    def validate_echo(input_data: object) -> object:
        return input_data

    def run_echo(_input_data: object, _context: ToolContext) -> ToolResult:
        return ToolResult(ok=True, output="echo")

    return ToolDefinition(
        name="echo",
        description="Echo text for tests.",
        input_schema={"type": "object"},
        validator=validate_echo,
        run=run_echo,
    )


def test_build_system_prompt_includes_runtime_context_and_registered_tools() -> None:
    prompt = build_system_prompt(
        cwd="D:/workspace/demo",
        tools=ToolRegistry([_echo_tool()]),
    )

    assert prompt == (
        "You are MiniCode Lite, a coding assistant.\n"
        "Current working directory: D:/workspace/demo\n"
        "Tools:\n"
        "- echo: Echo text for tests.\n"
        "Permissions: not configured\n"
        "Memory: not configured"
    )


def test_build_system_prompt_marks_an_empty_registry_explicitly() -> None:
    prompt = build_system_prompt(cwd="D:/workspace/empty", tools=ToolRegistry([]))

    assert "Current working directory: D:/workspace/empty" in prompt
    assert "Tools:\n- No tools registered." in prompt
    assert "Permissions: not configured" in prompt
    assert "Memory: not configured" in prompt


def test_build_system_prompt_includes_configured_permission_summary() -> None:
    class Permissions:
        def get_summary(self) -> list[str]:
            return ["workspace: D:/workspace/demo", "edits require approval"]

    prompt = build_system_prompt(
        cwd="D:/workspace/demo",
        tools=ToolRegistry([]),
        permissions=Permissions(),
    )

    assert "Permissions:\n- workspace: D:/workspace/demo\n- edits require approval" in prompt
    assert "Permissions: not configured" not in prompt


def test_build_system_prompt_injects_memory_context() -> None:
    prompt = build_system_prompt(
        cwd="D:/workspace/demo",
        tools=ToolRegistry([]),
        memory_context="- 文件编辑前必须创建 checkpoint。",
    )

    assert "Memory:\n- 文件编辑前必须创建 checkpoint。" in prompt
    assert "Memory: not configured" not in prompt


def test_build_system_prompt_marks_configured_memory_without_matches() -> None:
    prompt = build_system_prompt(
        cwd="D:/workspace/demo",
        tools=ToolRegistry([]),
        memory_context="",
    )

    assert "Memory:\n- No relevant project memories." in prompt
