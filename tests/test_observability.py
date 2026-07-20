from __future__ import annotations

import logging

from minicode_lite.agent_loop import run_agent_turn
from minicode_lite.mock_model import ScriptedModel
from minicode_lite.tooling import ToolContext, ToolDefinition, ToolRegistry, ToolResult
from minicode_lite.types import AgentStep


def _registry(*, succeeds: bool = True) -> ToolRegistry:
    return ToolRegistry(
        [
            ToolDefinition(
                name="observe",
                description="Test logging boundary.",
                input_schema={"type": "object"},
                validator=lambda value: value,
                run=lambda _value, _context: ToolResult(ok=succeeds, output="private-output"),
            )
        ]
    )


def test_tool_execution_emits_safe_structured_metadata(caplog) -> None:
    caplog.set_level(logging.INFO, logger="minicode_lite.tools")

    result = _registry().execute(
        "observe",
        {"token": "private-input"},
        ToolContext(cwd="."),
    )

    assert result.ok is True
    record = caplog.records[-1]
    assert record.tool_name == "observe"
    assert record.success is True
    assert record.duration_ms >= 0
    assert "private-input" not in record.getMessage()
    assert "private-output" not in record.getMessage()


def test_failed_tool_execution_is_logged_without_output(caplog) -> None:
    caplog.set_level(logging.INFO, logger="minicode_lite.tools")

    result = _registry(succeeds=False).execute("observe", {}, ToolContext(cwd="."))

    assert result.ok is False
    assert caplog.records[-1].success is False
    assert "private-output" not in caplog.records[-1].getMessage()


def test_agent_turn_logs_assistant_stop_reason(caplog) -> None:
    caplog.set_level(logging.INFO, logger="minicode_lite.agent_loop")

    run_agent_turn(
        model=ScriptedModel([AgentStep(type="assistant", content="done")]),
        tools=ToolRegistry([]),
        messages=[{"role": "user", "content": "finish"}],
        cwd=".",
    )

    record = caplog.records[-1]
    assert record.stop_reason == "assistant_final"
    assert record.steps == 1


def test_agent_turn_logs_max_steps_stop_reason(caplog) -> None:
    caplog.set_level(logging.INFO, logger="minicode_lite.agent_loop")
    model = ScriptedModel(
        [
            AgentStep(
                type="tool_calls",
                calls=[{"id": "call-1", "toolName": "observe", "input": {}}],
            )
        ]
    )

    run_agent_turn(
        model=model,
        tools=_registry(),
        messages=[{"role": "user", "content": "continue"}],
        cwd=".",
        max_steps=1,
        widening_extra_steps=0,
    )

    records = [record for record in caplog.records if record.name == "minicode_lite.agent_loop"]
    assert records[-1].stop_reason == "max_steps"
    assert records[-1].steps == 1
