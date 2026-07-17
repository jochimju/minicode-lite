from __future__ import annotations

from pathlib import Path

import pytest

from minicode_lite.permissions import PermissionManager, classify_dangerous_command


def test_workspace_read_is_allowed_without_prompt(tmp_path: Path) -> None:
    manager = PermissionManager(
        tmp_path,
        prompt_handler=lambda _request: pytest.fail("workspace read must not prompt"),
    )

    manager.ensure_path_access(str(tmp_path / "notes.txt"), "read")


def test_external_write_is_denied_without_prompt(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    manager = PermissionManager(workspace)

    with pytest.raises(PermissionError, match="outside workspace"):
        manager.ensure_path_access(str(tmp_path / "outside.txt"), "write")


def test_prompt_handler_can_allow_external_path_once(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    requests: list[dict[str, object]] = []

    def allow(request: dict[str, object]) -> dict[str, str]:
        requests.append(request)
        return {"decision": "allow_once"}

    manager = PermissionManager(workspace, prompt_handler=allow)
    target = tmp_path / "outside.txt"

    manager.ensure_path_access(str(target), "read")

    assert requests[0]["kind"] == "path"
    assert f"target: {target.resolve()}" in requests[0]["details"]


def test_turn_scoped_edit_approval_resets_after_turn(tmp_path: Path) -> None:
    target = tmp_path / "demo.py"
    prompts: list[dict[str, object]] = []

    def allow_turn(request: dict[str, object]) -> str:
        prompts.append(request)
        return "allow_turn"

    manager = PermissionManager(tmp_path, prompt_handler=allow_turn)
    manager.begin_turn()
    manager.ensure_edit(str(target), "- old\n+ new\n")
    manager.ensure_edit(str(target), "- old\n+ newer\n")

    assert len(prompts) == 1

    manager.end_turn()
    manager.ensure_edit(str(target), "- old\n+ newest\n")

    assert len(prompts) == 2


@pytest.mark.parametrize(
    ("command", "args", "expected"),
    [
        ("git", ["reset", "--hard"], "discard local changes"),
        ("git", ["push", "--force"], "rewrite remote history"),
        ("rm", ["-rf", "build"], "remove files"),
        ("python", ["script.py"], "arbitrary code"),
    ],
)
def test_dangerous_command_classification(
    command: str,
    args: list[str],
    expected: str,
) -> None:
    reason = classify_dangerous_command(command, args)

    assert reason is not None
    assert expected in reason
