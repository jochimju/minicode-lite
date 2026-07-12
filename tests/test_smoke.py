from __future__ import annotations

import io

import minicode_lite
from minicode_lite.main import READY_MESSAGE, run


def test_package_imports() -> None:
    assert minicode_lite.__version__ == "0.0.1"


def test_cli_ready_message() -> None:
    stdout = io.StringIO()

    exit_code = run([], stdout=stdout)

    assert exit_code == 0
    assert stdout.getvalue().strip() == READY_MESSAGE


def test_cli_version() -> None:
    stdout = io.StringIO()

    exit_code = run(["--version"], stdout=stdout)

    assert exit_code == 0
    assert stdout.getvalue().strip() == minicode_lite.__version__

