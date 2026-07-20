from __future__ import annotations

"""把本地技能读取能力包装成现有 ToolRegistry 可调用的工具。"""

from minicode_lite.skills import load_skill
from minicode_lite.tooling import ToolDefinition, ToolResult


def create_load_skill_tool(cwd: str) -> ToolDefinition:
    """创建绑定工作区的工具；正文只在模型明确请求时加载。"""
    def validate(data: object) -> dict[str, str]:
        if not isinstance(data, dict) or not isinstance(data.get("name"), str) or not data["name"].strip():
            raise ValueError("name is required")
        return {"name": data["name"].strip()}

    def run(data: dict[str, str], _context) -> ToolResult:
        skill = load_skill(cwd, data["name"])
        if skill is None:
            return ToolResult(False, f"Unknown skill: {data['name']}")
        return ToolResult(True, f"SKILL: {skill.name}\nSOURCE: {skill.source}\nPATH: {skill.path}\n\n{skill.content}")

    return ToolDefinition("load_skill", "Load a local SKILL.md by name.", {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}, validate, run)


__all__ = ["create_load_skill_tool"]
