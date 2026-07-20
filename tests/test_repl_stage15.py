from __future__ import annotations

import io
from pathlib import Path

from minicode_lite.mock_model import ScriptedModel
from minicode_lite.repl import Repl
from minicode_lite.tui.input_handler import classify_input
from minicode_lite.tui.tool_lifecycle import ToolLifecycle
from minicode_lite.types import AgentStep


def test_input_classification_routes_exit_local_and_agent() -> None:
    assert classify_input(" /exit ").kind == "exit"
    assert classify_input("/tools").kind == "local"
    assert classify_input("hello").kind == "agent"
    assert classify_input("  ").kind == "empty"


def test_tool_lifecycle_preserves_start_result_order_and_closes_dangling() -> None:
    lifecycle = ToolLifecycle()
    lifecycle.start("read_file", "1", {"path": "a.txt"})
    lifecycle.result("read_file", "1", "body")
    assert lifecycle.entries[0].state == "complete"
    lifecycle.start("write_file", "2")
    assert [entry.kind for entry in lifecycle.entries] == ["tool_start", "tool_result", "tool_start"]
    assert lifecycle.finalize() == 1
    assert lifecycle.entries[-1].state == "error"


def test_repl_runs_agent_and_local_command_without_model_for_local(tmp_path: Path) -> None:
    output = io.StringIO()
    model = ScriptedModel([AgentStep(type="assistant", content="answer")])
    repl = Repl(cwd=tmp_path, output=output, model_factory=lambda _config, _tools: (model, "test"))
    assert repl.run(["/tools", "hello", "/exit"]) == 0
    rendered = output.getvalue()
    assert "read_file" in rendered
    assert "answer" in rendered
    assert repl.session.messages[-1]["content"] == "answer"


def test_repl_displays_tool_lifecycle_before_assistant(tmp_path: Path) -> None:
    (tmp_path / "demo.txt").write_text("file body", encoding="utf-8")
    output = io.StringIO()
    model = ScriptedModel([
        AgentStep(type="tool_calls", calls=[{
            "id": "call-1", "toolName": "read_file", "input": {"path": "demo.txt"},
        }]),
        AgentStep(type="assistant", content="read complete"),
    ])
    repl = Repl(cwd=tmp_path, output=output, model_factory=lambda _config, _tools: (model, "test"))

    repl.run(["read demo.txt", "/exit"])

    rendered = output.getvalue()
    assert rendered.index("[tool:start] read_file") < rendered.index("[tool:result]")
    assert rendered.index("[tool:result]") < rendered.index("read complete")
    assert [entry.kind for entry in repl.transcript.entries] == [
        "user", "tool_start", "tool_result", "assistant",
    ]
