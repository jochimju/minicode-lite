from __future__ import annotations

from minicode_lite.types import AgentStep, ChatMessage, StepDiagnostics, ToolCall


def test_chat_message_and_tool_call_shapes_are_plain_data() -> None:
    message: ChatMessage = {"role": "user", "content": "read the file"}
    call: ToolCall = {
        "id": "call-1",
        "toolName": "read_file",
        "input": {"path": "demo.txt"},
    }

    assert message["role"] == "user"
    assert call["toolName"] == "read_file"
    assert call["input"] == {"path": "demo.txt"}


def test_agent_step_can_represent_assistant_and_tool_calls() -> None:
    assistant_step = AgentStep(type="assistant", content="done")
    tool_step = AgentStep(
        type="tool_calls",
        calls=[
            {
                "id": "call-1",
                "toolName": "read_file",
                "input": {"path": "demo.txt"},
            }
        ],
    )

    assert assistant_step.content == "done"
    assert assistant_step.calls == []
    assert tool_step.content == ""
    assert tool_step.calls[0]["toolName"] == "read_file"


def test_step_diagnostics_defaults_are_independent() -> None:
    first = StepDiagnostics()
    second = StepDiagnostics()

    first.blockTypes.append("empty_response")

    assert first.stopReason is None
    assert first.blockTypes == ["empty_response"]
    assert second.blockTypes == []
