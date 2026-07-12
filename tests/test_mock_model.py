from __future__ import annotations

import pytest

from minicode_lite.mock_model import MockModelAdapter, ScriptedModel
from minicode_lite.types import AgentStep, ChatMessage


def test_mock_model_returns_assistant_for_plain_input() -> None:
    model = MockModelAdapter()
    messages: list[ChatMessage] = [{"role": "user", "content": "hello"}]

    step = model.next(messages)

    assert step.type == "assistant"
    assert "MiniCode Lite" in step.content
    assert step.calls == []


def test_mock_model_turns_read_shortcut_into_tool_call() -> None:
    model = MockModelAdapter()
    messages: list[ChatMessage] = [{"role": "user", "content": "/read demo.txt"}]

    step = model.next(messages)

    assert step.type == "tool_calls"
    assert step.calls == [
        {
            "id": "mock-read-1",
            "toolName": "read_file",
            "input": {"path": "demo.txt"},
        }
    ]


def test_mock_model_summarizes_tool_result() -> None:
    model = MockModelAdapter()
    messages: list[ChatMessage] = [
        {"role": "user", "content": "/read demo.txt"},
        {
            "role": "assistant_tool_call",
            "content": "",
            "toolUseId": "mock-read-1",
            "toolName": "read_file",
            "input": {"path": "demo.txt"},
        },
        {
            "role": "tool_result",
            "content": "hello from file",
            "toolUseId": "mock-read-1",
            "toolName": "read_file",
            "isError": False,
        },
    ]

    step = model.next(messages)

    assert step.type == "assistant"
    assert step.content == "File contents:\n\nhello from file"


def test_scripted_model_returns_steps_in_order_and_records_messages() -> None:
    messages: list[ChatMessage] = [{"role": "user", "content": "start"}]
    model = ScriptedModel(
        [
            AgentStep(type="tool_calls", calls=[{"id": "1", "toolName": "echo", "input": {"text": "hi"}}]),
            AgentStep(type="assistant", content="done"),
        ]
    )

    first = model.next(messages)
    second = model.next(messages)

    assert first.type == "tool_calls"
    assert second.content == "done"
    assert model.calls == 2
    assert model.received_messages == [messages, messages]


def test_scripted_model_reports_clear_error_when_steps_are_exhausted() -> None:
    model = ScriptedModel([AgentStep(type="assistant", content="only step")])
    model.next([])

    with pytest.raises(IndexError, match="ScriptedModel has no step 2"):
        model.next([])
