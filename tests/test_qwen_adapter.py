from __future__ import annotations

from typing import Any

import pytest

from minicode_lite.qwen_adapter import QwenModelAdapter
from minicode_lite.tooling import ToolContext, ToolDefinition, ToolRegistry, ToolResult
from minicode_lite.types import ChatMessage


class FakeTransport:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.endpoint = ""
        self.headers: dict[str, str] = {}
        self.payload: dict[str, Any] = {}

    def __call__(
        self,
        endpoint: str,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.endpoint = endpoint
        self.headers = headers
        self.payload = payload
        return self.response


def make_tools() -> ToolRegistry:
    def validate_echo(input_data: object) -> dict[str, str]:
        assert isinstance(input_data, dict)
        return {"text": str(input_data["text"])}

    def run_echo(input_data: dict[str, str], _context: ToolContext) -> ToolResult:
        return ToolResult(ok=True, output=input_data["text"])

    return ToolRegistry(
        [
            ToolDefinition(
                name="echo",
                description="Echo text for tests.",
                input_schema={
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
                validator=validate_echo,
                run=run_echo,
            )
        ]
    )


def test_qwen_adapter_sends_openai_compatible_request_and_parses_text() -> None:
    transport = FakeTransport(
        {"choices": [{"message": {"content": "The task is complete."}}]}
    )
    model = QwenModelAdapter(
        model="qwen-plus",
        base_url="https://example.test/v1/",
        api_key="test-key",
        tools=make_tools(),
        transport=transport,
    )
    messages: list[ChatMessage] = [
        {"role": "system", "content": "Follow the rules."},
        {"role": "user", "content": "Say hello."},
        {"role": "assistant", "content": "I will help."},
        {
            "role": "assistant_tool_call",
            "content": "",
            "toolUseId": "call-echo-1",
            "toolName": "echo",
            "input": {"text": "hello"},
        },
        {
            "role": "tool_result",
            "content": "hello",
            "toolUseId": "call-echo-1",
            "toolName": "echo",
            "isError": False,
        },
    ]

    step = model.next(messages)

    assert transport.endpoint == "https://example.test/v1/chat/completions"
    assert transport.headers == {
        "Authorization": "Bearer test-key",
        "Content-Type": "application/json",
    }
    assert transport.payload["model"] == "qwen-plus"
    assert transport.payload["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "echo",
                "description": "Echo text for tests.",
                "parameters": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            },
        }
    ]
    assert transport.payload["messages"][:3] == [
        {"role": "system", "content": "Follow the rules."},
        {"role": "user", "content": "Say hello."},
        {"role": "assistant", "content": "I will help."},
    ]
    assert transport.payload["messages"][3] == {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "call-echo-1",
                "type": "function",
                "function": {
                    "name": "echo",
                    "arguments": '{"text":"hello"}',
                },
            }
        ],
    }
    assert transport.payload["messages"][4] == {
        "role": "tool",
        "tool_call_id": "call-echo-1",
        "content": "hello",
    }
    assert step.type == "assistant"
    assert step.content == "The task is complete."


def test_qwen_adapter_parses_tool_calls_and_json_object_arguments() -> None:
    transport = FakeTransport(
        {
            "choices": [
                {
                    "message": {
                        "content": "I will read the notes first.",
                        "tool_calls": [
                            {
                                "id": "call-read-1",
                                "type": "function",
                                "function": {
                                    "name": "read_file",
                                    "arguments": '{"path":"notes.txt"}',
                                },
                            }
                        ]
                    }
                }
            ]
        }
    )
    model = QwenModelAdapter(
        model="qwen-plus",
        base_url="https://example.test/v1",
        api_key="test-key",
        tools=ToolRegistry([]),
        transport=transport,
    )

    step = model.next([{"role": "user", "content": "Read my notes."}])

    assert step.type == "tool_calls"
    assert step.calls == [
        {
            "id": "call-read-1",
            "toolName": "read_file",
            "input": {"path": "notes.txt"},
        }
    ]


def test_qwen_adapter_serializes_progress_as_assistant_message() -> None:
    transport = FakeTransport(
        {"choices": [{"message": {"content": "The task is complete."}}]}
    )
    model = QwenModelAdapter(
        model="qwen-plus",
        base_url="https://example.test/v1",
        api_key="test-key",
        tools=ToolRegistry([]),
        transport=transport,
    )

    step = model.next(
        [{"role": "assistant_progress", "content": "Reading the notes..."}]
    )

    assert transport.payload["messages"] == [
        {"role": "assistant", "content": "Reading the notes..."}
    ]
    assert step.content == "The task is complete."


def test_qwen_adapter_rejects_non_function_provider_tool_call() -> None:
    model = QwenModelAdapter(
        model="qwen-plus",
        base_url="https://example.test/v1",
        api_key="test-key",
        tools=ToolRegistry([]),
        transport=FakeTransport(
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call-unknown-1",
                                    "type": "custom",
                                    "function": {
                                        "name": "read_file",
                                        "arguments": "{}",
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="Invalid Qwen-compatible response: tool call type must be 'function'\\.",
    ):
        model.next([{"role": "user", "content": "Read my notes."}])


@pytest.mark.parametrize(
    ("response", "message"),
    [
        ({}, "Invalid Qwen-compatible response"),
        ({"choices": [{"message": {}}]}, "Invalid Qwen-compatible response"),
    ],
)
def test_qwen_adapter_rejects_malformed_responses(
    response: dict[str, Any], message: str
) -> None:
    model = QwenModelAdapter(
        model="qwen-plus",
        base_url="https://example.test/v1",
        api_key="test-key",
        tools=ToolRegistry([]),
        transport=FakeTransport(response),
    )

    with pytest.raises(RuntimeError, match=message):
        model.next([{"role": "user", "content": "Hello."}])


def test_qwen_adapter_wraps_transport_errors_without_leaking_api_key() -> None:
    def failing_transport(
        _endpoint: str, _headers: dict[str, str], _payload: dict[str, Any]
    ) -> dict[str, Any]:
        raise OSError("connection refused")

    model = QwenModelAdapter(
        model="qwen-plus",
        base_url="https://example.test/v1",
        api_key="secret-key",
        tools=ToolRegistry([]),
        transport=failing_transport,
    )

    with pytest.raises(RuntimeError, match="Qwen-compatible request failed") as error:
        model.next([{"role": "user", "content": "Hello."}])

    assert "secret-key" not in str(error.value)
