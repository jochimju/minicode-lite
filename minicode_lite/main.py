from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import TextIO


READY_MESSAGE = "MiniCode Lite ready"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="minicode-lite",
        description="MiniCode Lite stage 0 command line entry point.",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print the package version and exit.",
    )
    return parser


def run(argv: Sequence[str] | None = None, stdout: TextIO | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    output = stdout
    if output is None:
        import sys

        output = sys.stdout

    if args.version:
        from minicode_lite import __version__

        print(__version__, file=output)
        return 0

    print(READY_MESSAGE, file=output)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run(argv)

