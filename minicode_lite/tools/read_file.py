from __future__ import annotations

# 定义读取工作区内 UTF-8 文本文件的只读工具。

from typing import Any

from minicode_lite.tooling import ToolContext, ToolDefinition, ToolResult
from minicode_lite.tools._shared import read_text_file, resolve_for_tool


def _validate(input_data: Any) -> dict[str, str]:
    """要求调用方提供非空路径，并返回仅含路径的规范输入。"""

    if not isinstance(input_data, dict):
        raise ValueError("input must be an object")
    path = input_data.get("path")
    if not isinstance(path, str) or not path:
        raise ValueError("path is required")
    return {"path": path}


def _run(input_data: dict[str, str], context: ToolContext) -> ToolResult:
    """先执行工作区边界检查，再使用共享函数安全读取文本。"""

    # read 模式留给后续权限系统区分读写操作。
    target, error = resolve_for_tool(context, input_data["path"], "read")
    if error is not None:
        return error
    # 成功解析后目标路径不再为空。
    assert target is not None

    # 共享函数处理不存在、目录、编码和二进制等文件细节。
    content, read_error = read_text_file(target, input_data["path"])
    if read_error is not None:
        return read_error
    # 没有错误结果时 content 必然是可返回给模型的文本。
    assert content is not None
    return ToolResult(ok=True, output=content)


# ToolDefinition 是模型可见的名称、描述、schema 与 Python 实现之间的桥梁。
read_file_tool = ToolDefinition(
    name="read_file",
    description="Read a UTF-8 text file relative to the workspace root.",
    input_schema={
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
    validator=_validate,
    run=_run,
)
