from __future__ import annotations

"""MCP 扩展点的可测试替身；阶段 14 不启动真实 stdio 客户端。"""

from dataclasses import dataclass
from typing import Any, Callable

from minicode_lite.tooling import ToolDefinition, ToolRegistry, ToolResult


@dataclass(frozen=True, slots=True)
class FakeMcpTool:
    """描述一个外部 MCP 工具，并将其适配为本地 runner。"""

    name: str  # 外部工具进入本地注册表后的调用名称。
    description: str  # 暴露给模型的用途说明。
    input_schema: dict[str, Any]  # 保留 MCP 工具声明的 JSON Schema。
    run: Callable[[Any], ToolResult]  # fake 传输层用同步函数模拟一次远端调用。


def register_fake_mcp_tools(registry: ToolRegistry, tools: list[FakeMcpTool]) -> ToolRegistry:
    """把 fake 工具注册到既有注册表；重复名称显式报错，避免静默覆盖。"""

    # 先检查整批名称，保证失败时注册表完全不变，不留下“只接入一半”的状态。
    names = [tool.name for tool in tools]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate tool names in MCP batch")
    for name in names:
        if registry.find(name) is not None:
            raise ValueError(f"Tool already registered: {name}")
    for external in tools:
        # 外部协议的输入校验暂用透传；真实 MCP 客户端将在未来负责 schema 校验和传输。
        definition = ToolDefinition(
            external.name,
            external.description,
            external.input_schema,
            lambda value: value,
            lambda value, _ctx, item=external: item.run(value),
        )
        registry.register(definition)
    return registry


__all__ = ["FakeMcpTool", "register_fake_mcp_tools"]
