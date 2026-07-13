from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from minicode_lite.headless import run_headless


READY_MESSAGE = "MiniCode Lite ready"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="minicode-lite",
        description="MiniCode Lite command line entry point.",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print the package version and exit.",
    )
    parser.add_argument(
        "prompt",
        nargs="*",
        help="Prompt to run once in headless mode.",
    )
    return parser


def run(
    argv: Sequence[str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    cwd: str | Path | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    output = stdout
    if output is None:
        import sys

        output = sys.stdout
    error_output = stderr
    if error_output is None:
        import sys

        error_output = sys.stderr

    if args.version:
        from minicode_lite import __version__

        print(__version__, file=output)
        return 0

    prompt = " ".join(args.prompt).strip()
    if prompt:
        try:
            print(run_headless(prompt, cwd=cwd), file=output)
        except ValueError as error:
            print(f"Error: {error}", file=error_output)
            return 1
        return 0

    print(READY_MESSAGE, file=output)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run(argv)
