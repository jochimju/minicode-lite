from __future__ import annotations

import argparse
from pathlib import Path
from typing import TextIO

from minicode_lite.agent_loop import run_agent_turn
from minicode_lite.local_commands import try_handle_local_command
from minicode_lite.mock_model import MockModelAdapter
from minicode_lite.tools import create_default_tool_registry
from minicode_lite.types import ChatMessage


def _last_assistant_content(messages: list[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.get("role") == "assistant":
            return message.get("content", "")
    return "(no response)"


def run_headless(prompt: str, *, cwd: str | Path | None = None) -> str:
    user_prompt = prompt.strip()
    if not user_prompt:
        raise ValueError("empty prompt")

    workspace = Path.cwd() if cwd is None else Path(cwd)
    tools = create_default_tool_registry()

    local_result = try_handle_local_command(user_prompt, tools=tools, cwd=workspace)
    if local_result is not None:
        return local_result

    messages: list[ChatMessage] = [{"role": "user", "content": user_prompt}]
    result_messages = run_agent_turn(
        model=MockModelAdapter(),
        tools=tools,
        messages=messages,
        cwd=str(workspace),
    )
    return _last_assistant_content(result_messages)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="minicode-lite-headless",
        description="Run one non-interactive MiniCode Lite turn.",
    )
    parser.add_argument("prompt", nargs="*", help="Prompt to send to the mock agent.")
    return parser


def run(argv: list[str] | None = None, stdout: TextIO | None = None, stderr: TextIO | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    import sys

    out = sys.stdout if stdout is None else stdout
    err = sys.stderr if stderr is None else stderr
    prompt = " ".join(args.prompt).strip()
    if not prompt:
        print("Error: empty prompt", file=err)
        return 1

    try:
        print(run_headless(prompt), file=out)
    except ValueError as error:
        print(f"Error: {error}", file=err)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    return run(argv)
