from __future__ import annotations

import pytest

from minicode_lite.agent_loop import run_agent_turn
from minicode_lite.mock_model import ScriptedModel
from minicode_lite.tooling import ToolContext, ToolDefinition, ToolRegistry, ToolResult
from minicode_lite.types import AgentStep, ChatMessage


def _echo_registry() -> ToolRegistry:
    def validate_echo(input_data: object) -> dict[str, str]:
        assert isinstance(input_data, dict)
        return {"text": str(input_data["text"])}

    def run_echo(input_data: dict[str, str], _context: ToolContext) -> ToolResult:
        return ToolResult(ok=True, output=f"echo:{input_data['text']}")

    return ToolRegistry(
        [
            ToolDefinition(
                name="echo",
                description="Echo text for agent loop tests.",
                input_schema={"type": "object"},
                validator=validate_echo,
                run=run_echo,
            )
        ]
    )


def test_agent_turn_executes_tool_and_returns_final_assistant() -> None:
    model = ScriptedModel(
        [
            AgentStep(
                type="tool_calls",
                calls=[{"id": "call-1", "toolName": "echo", "input": {"text": "hi"}}],
            ),
            AgentStep(type="assistant", content="done"),
        ]
    )

    messages = run_agent_turn(
        model=model,
        tools=_echo_registry(),
        messages=[{"role": "user", "content": "say hi through echo"}],
        cwd=".",
    )

    assert messages[-1] == {"role": "assistant", "content": "done"}
    assert {
        "role": "assistant_tool_call",
        "content": "",
        "toolUseId": "call-1",
        "toolName": "echo",
        "input": {"text": "hi"},
    } in messages
    assert {
        "role": "tool_result",
        "content": "echo:hi",
        "toolUseId": "call-1",
        "toolName": "echo",
        "isError": False,
    } in messages
    assert model.calls == 2
    assert model.received_messages[1][-1]["role"] == "tool_result"


def test_agent_turn_records_all_tool_intents_before_the_first_tool_result() -> None:
    model = ScriptedModel(
        [
            AgentStep(
                type="tool_calls",
                calls=[
                    {"id": "call-1", "toolName": "echo", "input": {"text": "first"}},
                    {"id": "call-2", "toolName": "echo", "input": {"text": "second"}},
                ],
            ),
            AgentStep(type="assistant", content="done"),
        ]
    )

    messages = run_agent_turn(
        model=model,
        tools=_echo_registry(),
        messages=[{"role": "user", "content": "run both echoes"}],
        cwd=".",
    )

    first_result_index = next(
        index for index, message in enumerate(messages) if message["role"] == "tool_result"
    )
    assert messages[1:first_result_index] == [
        {
            "role": "assistant_tool_call",
            "content": "",
            "toolUseId": "call-1",
            "toolName": "echo",
            "input": {"text": "first"},
        },
        {
            "role": "assistant_tool_call",
            "content": "",
            "toolUseId": "call-2",
            "toolName": "echo",
            "input": {"text": "second"},
        },
    ]


def test_agent_turn_retries_empty_assistant_response_once() -> None:
    model = ScriptedModel(
        [
            AgentStep(type="assistant", content=""),
            AgentStep(type="assistant", content="done after retry"),
        ]
    )

    messages = run_agent_turn(
        model=model,
        tools=ToolRegistry([]),
        messages=[{"role": "user", "content": "continue"}],
        cwd=".",
    )

    assert messages[-1] == {"role": "assistant", "content": "done after retry"}
    assert any(
        message["role"] == "user" and "last response was empty" in message["content"]
        for message in messages
    )


def test_agent_turn_stops_after_repeated_empty_assistant_response() -> None:
    model = ScriptedModel(
        [
            AgentStep(type="assistant", content=""),
            AgentStep(type="assistant", content=""),
        ]
    )

    messages = run_agent_turn(
        model=model,
        tools=ToolRegistry([]),
        messages=[{"role": "user", "content": "continue"}],
        cwd=".",
    )

    assert messages[-1]["role"] == "assistant"
    assert "empty response" in messages[-1]["content"].lower()


def test_agent_turn_stops_when_max_steps_is_reached() -> None:
    model = ScriptedModel(
        [
            AgentStep(
                type="tool_calls",
                calls=[{"id": "call-1", "toolName": "echo", "input": {"text": "hi"}}],
            ),
            AgentStep(type="assistant", content="would be too late"),
        ]
    )

    messages = run_agent_turn(
        model=model,
        tools=_echo_registry(),
        messages=[{"role": "user", "content": "loop"}],
        cwd=".",
        max_steps=1,
    )

    assert messages[-1]["role"] == "assistant"
    assert "max_steps=1" in messages[-1]["content"]
    assert model.calls == 1


def test_agent_turn_emits_lifecycle_callbacks() -> None:
    events: list[tuple[str, str, bool | None]] = []
    model = ScriptedModel(
        [
            AgentStep(
                type="tool_calls",
                calls=[{"id": "call-1", "toolName": "echo", "input": {"text": "hi"}}],
            ),
            AgentStep(type="assistant", content="done"),
        ]
    )

    run_agent_turn(
        model=model,
        tools=_echo_registry(),
        messages=[{"role": "user", "content": "say hi"}],
        cwd=".",
        on_tool_start=lambda name, _input: events.append(("start", name, None)),
        on_tool_result=lambda name, _output, is_error: events.append(("result", name, is_error)),
        on_assistant_message=lambda content: events.append(("assistant", content, None)),
    )

    assert events == [
        ("start", "echo", None),
        ("result", "echo", False),
        ("assistant", "done", None),
    ]


def test_agent_turn_does_not_mutate_input_messages() -> None:
    initial: list[ChatMessage] = [{"role": "user", "content": "hello"}]
    model = ScriptedModel([AgentStep(type="assistant", content="done")])

    messages = run_agent_turn(
        model=model,
        tools=ToolRegistry([]),
        messages=initial,
        cwd=".",
    )

    assert initial == [{"role": "user", "content": "hello"}]
    assert messages != initial


def test_agent_turn_closes_permission_lifecycle_after_model_error() -> None:
    events: list[str] = []

    class Permissions:
        def begin_turn(self) -> None:
            events.append("begin")

        def end_turn(self) -> None:
            events.append("end")

    class FailingModel:
        def next(self, _messages: list[ChatMessage], store: object | None = None) -> AgentStep:
            del store
            raise RuntimeError("model failed")

    with pytest.raises(RuntimeError, match="model failed"):
        run_agent_turn(
            model=FailingModel(),
            tools=ToolRegistry([]),
            messages=[{"role": "user", "content": "hello"}],
            cwd=".",
            permissions=Permissions(),
        )

    assert events == ["begin", "end"]
