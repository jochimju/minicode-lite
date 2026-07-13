from __future__ import annotations

from collections.abc import Callable
from typing import Any

from minicode_lite.tooling import ToolContext, ToolRegistry, ToolResult
from minicode_lite.types import ChatMessage, ModelAdapter, ToolCall


EMPTY_RESPONSE_RETRY_MESSAGE = (
    "Your last response was empty. Please continue with a tool call or a final answer."
)


def _snapshot_messages(messages: list[ChatMessage]) -> list[ChatMessage]:
    return [dict(message) for message in messages]


def _append_assistant_message(
    messages: list[ChatMessage],
    content: str,
    on_assistant_message: Callable[[str], None] | None,
) -> None:
    messages.append({"role": "assistant", "content": content})
    if on_assistant_message is not None:
        on_assistant_message(content)


def _append_tool_call_message(messages: list[ChatMessage], call: ToolCall) -> None:
    messages.append(
        {
            "role": "assistant_tool_call",
            "content": "",
            "toolUseId": call["id"],
            "toolName": call["toolName"],
            "input": call["input"],
        }
    )


def _append_tool_result_message(
    messages: list[ChatMessage],
    call: ToolCall,
    result: ToolResult,
) -> None:
    messages.append(
        {
            "role": "tool_result",
            "content": result.output,
            "toolUseId": call["id"],
            "toolName": call["toolName"],
            "isError": not result.ok,
        }
    )


def run_agent_turn(
    *,
    model: ModelAdapter,
    tools: ToolRegistry,
    messages: list[ChatMessage],
    cwd: str,
    max_steps: int = 8,
    permissions: Any | None = None,
    session: Any | None = None,
    runtime: dict[str, Any] | None = None,
    store: Any | None = None,
    on_tool_start: Callable[[str, Any], None] | None = None,
    on_tool_result: Callable[[str, str, bool], None] | None = None,
    on_assistant_message: Callable[[str], None] | None = None,
    on_progress_message: Callable[[str], None] | None = None,
) -> list[ChatMessage]:
    working_messages = _snapshot_messages(messages)
    empty_response_retried = False

    for _step_index in range(max_steps):
        next_step = model.next(
            _snapshot_messages(working_messages),
            store=store,
        )

        if next_step.type == "assistant":
            content = next_step.content
            if next_step.kind == "progress" or next_step.contentKind == "progress":
                if content:
                    working_messages.append({"role": "assistant_progress", "content": content})
                    if on_progress_message is not None:
                        on_progress_message(content)
                continue

            if not content.strip():
                if empty_response_retried:
                    _append_assistant_message(
                        working_messages,
                        "Stopped because the model returned an empty response twice.",
                        on_assistant_message,
                    )
                    return working_messages
                empty_response_retried = True
                working_messages.append({"role": "user", "content": EMPTY_RESPONSE_RETRY_MESSAGE})
                continue

            _append_assistant_message(working_messages, content, on_assistant_message)
            return working_messages

        if next_step.type == "tool_calls":
            for call in next_step.calls:
                _append_tool_call_message(working_messages, call)
                if on_tool_start is not None:
                    on_tool_start(call["toolName"], call["input"])

                result = tools.execute(
                    call["toolName"],
                    call["input"],
                    ToolContext(
                        cwd=cwd,
                        permissions=permissions,
                        session=session,
                        runtime=runtime,
                    ),
                )

                if on_tool_result is not None:
                    on_tool_result(call["toolName"], result.output, not result.ok)
                _append_tool_result_message(working_messages, call, result)
            continue

        _append_assistant_message(
            working_messages,
            f"Stopped because the model returned an unsupported step type: {next_step.type}",
            on_assistant_message,
        )
        return working_messages

    _append_assistant_message(
        working_messages,
        f"Stopped after reaching max_steps={max_steps}.",
        on_assistant_message,
    )
    return working_messages
