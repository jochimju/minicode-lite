from __future__ import annotations

# 处理不需要模型推理的本地 slash 命令，并将其他输入交回 agent。

from pathlib import Path

from minicode_lite.tooling import ToolContext, ToolRegistry


def format_tools(tools: ToolRegistry) -> str:
    """把当前注册表转成稳定、适合终端显示的“名称: 描述”列表。"""

    # 复用注册表保存的顺序，输出与默认工具注册顺序一致。
    return "\n".join(f"{tool.name}: {tool.description}" for tool in tools.list())


def try_handle_local_command(
    user_input: str,
    *,
    tools: ToolRegistry,
    cwd: str | Path,
) -> str | None:
    """尝试本地处理输入；返回 None 明确表示应交给模型执行。"""

    # 忽略首尾空白，保证命令判断不受终端输入格式影响。
    text = user_input.strip()
    if text == "/tools":
        return format_tools(tools)

    if text.startswith("/read "):
        # `/read` 是快捷方式：直接把路径翻译为 read_file 工具调用。
        path = text[len("/read ") :].strip()
        if not path:
            return "Usage: /read <path>"
        # 构造与 agent loop 完全相同的 ToolContext，使路径边界规则保持一致。
        result = tools.execute(
            "read_file",
            {"path": path},
            ToolContext(cwd=str(cwd)),
        )
        # 不论成功还是失败都返回工具输出，用户能直接看到文件内容或错误原因。
        return result.output

    # 未识别命令/普通文本由调用方交给 model -> tool -> model 主循环。
    return None
