from __future__ import annotations

import json
from pathlib import Path

from minicode_lite.config import RuntimeConfig
from minicode_lite.readiness import (
    READINESS_SCHEMA_VERSION,
    build_readiness_report,
    format_readiness_json,
    format_readiness_text,
)
from minicode_lite.tooling import ToolContext, ToolDefinition, ToolRegistry, ToolResult


def _configured_runtime() -> RuntimeConfig:
    return RuntimeConfig(
        model="qwen-plus",
        base_url="https://example.invalid/v1",
        api_key="stage12-secret",
        diagnostic="Qwen runtime configuration is complete.",
    )


def _mock_runtime() -> RuntimeConfig:
    return RuntimeConfig(
        model="",
        base_url="",
        api_key="",
        diagnostic=(
            "Qwen runtime configuration is incomplete; missing: "
            "MINI_CODE_MODEL, CUSTOM_API_BASE_URL, CUSTOM_API_KEY."
        ),
    )


def _one_tool_registry() -> ToolRegistry:
    return ToolRegistry(
        [
            ToolDefinition(
                name="noop",
                description="Test readiness tool.",
                input_schema={"type": "object"},
                validator=lambda value: value,
                run=lambda _value, _context: ToolResult(ok=True, output="ok"),
            )
        ]
    )


def test_readiness_json_schema_is_stable(tmp_path: Path) -> None:
    report = build_readiness_report(tmp_path, _one_tool_registry(), config=_configured_runtime())
    payload = json.loads(format_readiness_json(report))

    assert list(payload) == [
        "checks",
        "cwd",
        "mode",
        "python_version",
        "schema_version",
        "status",
    ]
    assert payload["schema_version"] == READINESS_SCHEMA_VERSION
    assert payload["status"] == "ready"
    assert payload["mode"] == "qwen"
    assert [check["name"] for check in payload["checks"]] == ["python", "cwd", "tools", "model"]
    assert all(set(check) == {"name", "status", "summary"} for check in payload["checks"])
    assert "stage12-secret" not in format_readiness_json(report)


def test_missing_model_configuration_is_mock_ready_warning(tmp_path: Path) -> None:
    report = build_readiness_report(tmp_path, _one_tool_registry(), config=_mock_runtime())

    assert report.status == "warning"
    assert report.mode == "mock"
    model_check = next(check for check in report.checks if check.name == "model")
    assert model_check.status == "warning"
    assert "Mock fallback is ready" in model_check.summary


def test_empty_tool_registry_blocks_readiness(tmp_path: Path) -> None:
    report = build_readiness_report(tmp_path, ToolRegistry([]), config=_mock_runtime())

    assert report.status == "blocked"
    assert next(check for check in report.checks if check.name == "tools").status == "blocked"
    assert "Readiness: blocked" in format_readiness_text(report)


def test_missing_workspace_blocks_readiness(tmp_path: Path) -> None:
    missing = tmp_path / "missing"

    report = build_readiness_report(missing, _one_tool_registry(), config=_configured_runtime())

    assert report.status == "blocked"
    assert next(check for check in report.checks if check.name == "cwd").summary == "Workspace does not exist."
