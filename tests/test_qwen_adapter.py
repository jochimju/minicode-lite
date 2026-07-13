from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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


def test_qwen_adapter_collapses_consecutive_tool_calls_into_one_provider_message() -> None:
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

    model.next(
        [
            {"role": "user", "content": "Run both tools."},
            {
                "role": "assistant_tool_call",
                "content": "",
                "toolUseId": "call-first",
                "toolName": "first_tool",
                "input": {"number": 1},
            },
            {
                "role": "assistant_tool_call",
                "content": "",
                "toolUseId": "call-second",
                "toolName": "second_tool",
                "input": {"number": 2},
            },
        ]
    )

    assert transport.payload["messages"] == [
        {"role": "user", "content": "Run both tools."},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call-first",
                    "type": "function",
                    "function": {"name": "first_tool", "arguments": '{"number":1}'},
                },
                {
                    "id": "call-second",
                    "type": "function",
                    "function": {"name": "second_tool", "arguments": '{"number":2}'},
                },
            ],
        },
    ]


def test_qwen_adapter_default_transport_does_not_follow_redirects_with_authorization() -> None:
    target_headers: list[dict[str, str]] = []

    class TargetHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            target_headers.append(dict(self.headers.items()))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"choices":[{"message":{"content":"unexpected"}}]}')

        def log_message(self, _format: str, *_args: object) -> None:
            return

    target_server = ThreadingHTTPServer(("127.0.0.1", 0), TargetHandler)
    target_thread = threading.Thread(target=target_server.serve_forever, daemon=True)
    target_thread.start()

    class RedirectHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            self.send_response(302)
            self.send_header(
                "Location",
                f"http://127.0.0.1:{target_server.server_port}/redirect-target",
            )
            self.end_headers()

        def log_message(self, _format: str, *_args: object) -> None:
            return

    redirect_server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
    redirect_thread = threading.Thread(target=redirect_server.serve_forever, daemon=True)
    redirect_thread.start()

    try:
        model = QwenModelAdapter(
            model="qwen-plus",
            base_url=f"http://127.0.0.1:{redirect_server.server_port}/v1",
            api_key="secret-key",
            tools=ToolRegistry([]),
        )

        with pytest.raises(
            RuntimeError,
            match="Qwen-compatible request failed with HTTP status 302\\.",
        ):
            model.next([{"role": "user", "content": "Hello."}])
    finally:
        redirect_server.shutdown()
        redirect_server.server_close()
        target_server.shutdown()
        target_server.server_close()
        redirect_thread.join()
        target_thread.join()

    assert target_headers == []


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
