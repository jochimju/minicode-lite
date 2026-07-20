from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

from minicode_lite import release_gate


def _completed(command: list[str], stdout: str = "ok\n", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, returncode, stdout, "")


def test_release_gate_runs_all_checks_and_validates_machine_outputs(
    tmp_path: Path, monkeypatch
) -> None:
    commands: list[list[str]] = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        joined = " ".join(command)
        if "/readiness --json" in joined:
            return _completed(
                command,
                json.dumps({"schema_version": "1.0", "status": "warning", "checks": []}),
            )
        if "release smoke" in joined:
            return _completed(command, "MiniCode Lite mock model received your message.\n")
        return _completed(command)

    monkeypatch.setattr(release_gate.subprocess, "run", fake_run)

    report = release_gate.run_release_gate(tmp_path)

    assert report.status == "pass"
    assert [check.name for check in report.checks] == [
        "compile",
        "import",
        "pytest",
        "readiness_json",
        "headless_smoke",
    ]
    assert len(commands) == 5


def test_release_gate_fails_on_invalid_readiness_json(tmp_path: Path, monkeypatch) -> None:
    def fake_run(command, **_kwargs):
        joined = " ".join(command)
        if "/readiness --json" in joined:
            return _completed(command, "not-json")
        if "release smoke" in joined:
            return _completed(command, "MiniCode Lite mock model received your message.\n")
        return _completed(command)

    monkeypatch.setattr(release_gate.subprocess, "run", fake_run)

    report = release_gate.run_release_gate(tmp_path)

    assert report.status == "fail"
    readiness = next(check for check in report.checks if check.name == "readiness_json")
    assert readiness.status == "fail"


def test_release_gate_cli_json_uses_exit_code_and_schema(tmp_path: Path, monkeypatch) -> None:
    report = release_gate.ReleaseReport(
        schema_version="1.0",
        status="pass",
        cwd=str(tmp_path),
        checks=(release_gate.ReleaseCheck("pytest", "pass", "tests passed"),),
    )
    monkeypatch.setattr(release_gate, "run_release_gate", lambda _cwd: report)
    output = io.StringIO()

    exit_code = release_gate.run(["--cwd", str(tmp_path), "--json"], stdout=output)

    assert exit_code == 0
    payload = json.loads(output.getvalue())
    assert payload["schema_version"] == "1.0"
    assert payload["checks"][0]["name"] == "pytest"
