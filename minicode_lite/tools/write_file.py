from __future__ import annotations

# 定义在工作区内创建或覆盖 UTF-8 文本文件的写入工具。

from typing import Any

from minicode_lite.tooling import ToolContext, ToolDefinition, ToolResult
from minicode_lite.tools._shared import (
    build_diff_preview,
    ensure_edit_for_tool,
    read_text_file,
    resolve_for_tool,
    write_text_file,
)


def _validate(input_data: Any) -> dict[str, str]:
    """验证写入操作同时拥有目标路径和文本内容。"""

    if not isinstance(input_data, dict):
        raise ValueError("input must be an object")
    # 路径和内容分别取出后独立校验，错误信息更利于模型修正调用。
    path = input_data.get("path")
    content = input_data.get("content")
    if not isinstance(path, str) or not path:
        raise ValueError("path is required")
    if not isinstance(content, str):
        raise ValueError("content must be a string")
    return {"path": path, "content": content}


def _run(input_data: dict[str, str], context: ToolContext) -> ToolResult:
    """确认写入路径可访问后，委托共享函数创建目录并写入文本。"""

    # write 模式让未来权限层能对有副作用操作采用更严格策略。
    target, error = resolve_for_tool(context, input_data["path"], "write")
    if error is not None:
        return error
    # 无权限错误即代表已获得可用规范化路径。
    assert target is not None
    # 覆盖已有文件时先读取旧内容，审批界面才能展示真实前后差异。
    before = ""
    if target.exists():
        before_content, read_error = read_text_file(target, input_data["path"])
        if read_error is not None:
            return read_error
        assert before_content is not None
        before = before_content
    preview = build_diff_preview(input_data["path"], before, input_data["content"])
    approval_error = ensure_edit_for_tool(context, target, preview)
    if approval_error is not None:
        return approval_error
    return write_text_file(target, input_data["path"], input_data["content"])


# 注册定义同时供 agent loop 和 `/tools` 命令使用。
write_file_tool = ToolDefinition(
    name="write_file",
    description="Write a UTF-8 text file relative to the workspace root.",
    input_schema={
        "type": "object",
        "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
        "required": ["path", "content"],
    },
    validator=_validate,
    run=_run,
)
