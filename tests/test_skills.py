from pathlib import Path

from minicode_lite.mcp import FakeMcpTool, register_fake_mcp_tools
from minicode_lite.headless import run_headless
from minicode_lite.mock_model import ScriptedModel
from minicode_lite.skills import discover_skills, extract_description, load_skill
from minicode_lite.tooling import ToolContext, ToolRegistry, ToolResult
from minicode_lite.tools.load_skill import create_load_skill_tool
from minicode_lite.types import AgentStep


def make_skill(root: Path, name: str, content: str) -> Path:
    skill_file = root / ".mini-code" / "skills" / name / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text(content, encoding="utf-8")
    return skill_file


def test_discover_skills_returns_project_metadata(tmp_path: Path) -> None:
    skill_file = make_skill(tmp_path, "review", "# Review\n\nReview changed Python files carefully.")

    skills = discover_skills(tmp_path, home=tmp_path / "home")

    assert len(skills) == 1
    assert skills[0].name == "review"
    assert skills[0].description == "Review changed Python files carefully."
    assert skills[0].path == str(skill_file)
    assert skills[0].source == "project"
    assert not hasattr(skills[0], "content")


def test_discover_skills_returns_empty_list_when_roots_do_not_exist(tmp_path: Path) -> None:
    assert discover_skills(tmp_path, home=tmp_path / "home") == []


def test_project_skill_wins_over_same_named_user_skill(tmp_path: Path) -> None:
    make_skill(tmp_path, "review", "Project instructions")
    home = tmp_path / "home"
    make_skill(home, "review", "User instructions")

    skill = load_skill(tmp_path, "review", home=home)

    assert skill is not None
    assert skill.source == "project"
    assert skill.content == "Project instructions"


def test_load_skill_rejects_path_traversal(tmp_path: Path) -> None:
    assert load_skill(tmp_path, "../secret") is None
    assert load_skill(tmp_path, "folder/name") is None


def test_extract_description_has_stable_fallback() -> None:
    assert extract_description("# Heading\n\n## Details") == "No description provided."


def test_load_skill_tool_reads_content(tmp_path: Path) -> None:
    make_skill(tmp_path, "testing", "# Testing\n\nAlways run focused tests.")
    registry = ToolRegistry([create_load_skill_tool(str(tmp_path))])

    result = registry.execute("load_skill", {"name": "testing"}, ToolContext(cwd=str(tmp_path)))

    assert result.ok is True
    assert "SKILL: testing" in result.output
    assert "Always run focused tests." in result.output


def test_load_skill_tool_reports_unknown_and_invalid_names(tmp_path: Path) -> None:
    registry = ToolRegistry([create_load_skill_tool(str(tmp_path))])
    context = ToolContext(cwd=str(tmp_path))

    assert registry.execute("load_skill", {"name": "missing"}, context) == ToolResult(False, "Unknown skill: missing")
    invalid = registry.execute("load_skill", {}, context)
    assert invalid.ok is False
    assert "name is required" in invalid.output


def test_headless_exposes_skill_metadata_and_load_tool(tmp_path: Path, monkeypatch) -> None:
    make_skill(tmp_path, "testing", "# Testing\n\nRun focused tests first.")
    monkeypatch.setenv("MINI_CODE_MODEL", "")
    monkeypatch.setenv("CUSTOM_API_BASE_URL", "")
    monkeypatch.setenv("CUSTOM_API_KEY", "")
    monkeypatch.setattr("minicode_lite.session.SESSIONS_DIR", tmp_path / "sessions")
    model = ScriptedModel([AgentStep(type="assistant", content="ready")])
    captured: dict[str, ToolRegistry] = {}

    def create_adapter(_config, tools):
        captured["tools"] = tools
        return model, "test"

    monkeypatch.setattr("minicode_lite.headless.create_model_adapter", create_adapter)

    assert run_headless("use the testing skill", cwd=tmp_path) == "ready"
    system_prompt = model.received_messages[0][0]["content"]
    assert "Skills:\n- testing: Run focused tests first. (project)" in system_prompt
    assert captured["tools"].find("load_skill") is not None


def test_fake_mcp_tool_registers_and_executes_through_registry(tmp_path: Path) -> None:
    registry = ToolRegistry([])
    external = FakeMcpTool(
        name="mcp_echo",
        description="Echo text through a fake MCP source.",
        input_schema={"type": "object"},
        run=lambda data: ToolResult(True, data["text"]),
    )

    returned = register_fake_mcp_tools(registry, [external])
    result = registry.execute("mcp_echo", {"text": "hello"}, ToolContext(cwd=str(tmp_path)))

    assert returned is registry
    assert result == ToolResult(True, "hello")


def test_fake_mcp_registration_rejects_duplicate_names() -> None:
    tool = FakeMcpTool("duplicate", "first", {}, lambda _data: ToolResult(True, "ok"))
    registry = ToolRegistry([])
    register_fake_mcp_tools(registry, [tool])

    try:
        register_fake_mcp_tools(registry, [tool])
    except ValueError as error:
        assert str(error) == "Tool already registered: duplicate"
    else:
        raise AssertionError("duplicate registration should fail")


def test_fake_mcp_batch_is_atomic_when_a_name_conflicts() -> None:
    existing = FakeMcpTool("existing", "existing", {}, lambda _data: ToolResult(True, "ok"))
    new = FakeMcpTool("new", "new", {}, lambda _data: ToolResult(True, "ok"))
    registry = ToolRegistry([])
    register_fake_mcp_tools(registry, [existing])

    try:
        register_fake_mcp_tools(registry, [new, existing])
    except ValueError:
        pass

    assert registry.find("new") is None
