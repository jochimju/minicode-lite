from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from minicode_lite.types import AgentStep, ChatMessage


def _last_user_message(messages: list[ChatMessage]) -> str:
    return next(
        (message.get("content", "") for message in reversed(messages) if message.get("role") == "user"),
        "",
    )


def _last_tool_result(messages: list[ChatMessage]) -> ChatMessage | None:
    return next(
        (message for message in reversed(messages) if message.get("role") == "tool_result"),
        None,
    )


def _latest_assistant_tool_name(messages: list[ChatMessage]) -> str | None:
    call = next(
        (message for message in reversed(messages) if message.get("role") == "assistant_tool_call"),
        None,
    )
    if call is None:
        return None
    return call.get("toolName")


class ScriptedModel:
    def __init__(self, steps: Iterable[AgentStep]) -> None:
        self._steps = list(steps)
        self.calls = 0
        self.received_messages: list[list[ChatMessage]] = []

    def next(
        self,
        messages: list[ChatMessage],
        on_stream_chunk: Callable[[str], None] | None = None,
        store: Any | None = None,
    ) -> AgentStep:
        del on_stream_chunk, store
        self.received_messages.append(messages)
        if self.calls >= len(self._steps):
            raise IndexError(f"ScriptedModel has no step {self.calls + 1}")
        step = self._steps[self.calls]
        self.calls += 1
        return step


class MockModelAdapter:
    def next(
        self,
        messages: list[ChatMessage],
        on_stream_chunk: Callable[[str], None] | None = None,
        store: Any | None = None,
    ) -> AgentStep:
        del on_stream_chunk, store
        tool_result = _last_tool_result(messages)
        if tool_result is not None:
            tool_name = _latest_assistant_tool_name(messages) or tool_result.get("toolName")
            content = tool_result.get("content", "")
            if tool_name == "read_file":
                return AgentStep(type="assistant", content=f"File contents:\n\n{content}")
            return AgentStep(type="assistant", content=f"I received the tool result:\n\n{content}")

        user_text = _last_user_message(messages).strip()
        if user_text.startswith("/read "):
            path = user_text[len("/read ") :].strip()
            return AgentStep(
                type="tool_calls",
                calls=[
                    {
                        "id": "mock-read-1",
                        "toolName": "read_file",
                        "input": {"path": path},
                    }
                ],
            )

        return AgentStep(
            type="assistant",
            content="MiniCode Lite mock model received your message.",
        )
