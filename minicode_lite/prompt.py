from __future__ import annotations

"""根据当前运行环境生成稳定的 system prompt。"""

from typing import Any

from minicode_lite.tooling import ToolRegistry


def build_system_prompt(
    *,
    cwd: str,
    tools: ToolRegistry,
    permissions: Any | None = None,
) -> str:
    """把工作目录、已注册工具和暂未实现的运行时能力写入模型可读提示。"""

    # 先写入不会随运行变化的助手身份，确保每次调用都以同一角色开场。
    lines = [
        "You are MiniCode Lite, a coding assistant.",
        # cwd 由调用方提供，保留原样才能让模型看到准确的运行位置。
        f"Current working directory: {cwd}",
        # 工具标题独占一行，让后续清单具有稳定且容易解析的结构。
        "Tools:",
    ]
    # 通过公开的 list 方法取得副本，同时沿用注册表定义的注册顺序。
    registered_tools = tools.list()
    if registered_tools:
        # 每个工具只暴露名称和面向模型的描述，不泄露运行函数等内部实现。
        for tool in registered_tools:
            lines.append(f"- {tool.name}: {tool.description}")
    else:
        # 空注册表也写出显式标记，避免模型误以为工具清单意外截断。
        lines.append("- No tools registered.")
    if permissions is None:
        # 独立调用 prompt 构建器时保留明确占位，不虚构运行时策略。
        lines.append("Permissions: not configured")
    else:
        # 权限管理器只暴露非敏感摘要，不把 prompt handler 或临时授权状态写给模型。
        lines.append("Permissions:")
        lines.extend(f"- {item}" for item in permissions.get_summary())
    # memory 仍属于后续阶段，继续显式标明尚未配置。
    lines.append("Memory: not configured")
    # 使用固定换行符连接各段，使相同输入始终生成相同的提示文本。
    return "\n".join(lines)
