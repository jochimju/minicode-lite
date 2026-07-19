from __future__ import annotations

# 定义精确文本替换工具，用匹配数保护避免模糊编辑。

from typing import Any

from minicode_lite.tooling import ToolContext, ToolDefinition, ToolResult
from minicode_lite.tools._shared import (
    build_diff_preview,
    checkpoint_for_tool,
    ensure_edit_for_tool,
    read_text_file,
    resolve_for_tool,
    write_text_file,
)


def _validate(input_data: Any) -> dict[str, Any]:
    """校验编辑参数，兼容两组字段别名并统一换行符。"""

    if not isinstance(input_data, dict):
        raise ValueError("input must be an object")
    # old/search 与 new/replace 兼容不同调用方，但内部只保留统一字段名。
    path = input_data.get("path")
    old = input_data.get("old", input_data.get("search"))
    new = input_data.get("new", input_data.get("replace"))
    # 兼容 snake_case 和 camelCase，最终转换为明确布尔值。
    replace_all = bool(input_data.get("replace_all", input_data.get("replaceAll", False)))

    if not isinstance(path, str) or not path:
        raise ValueError("path is required")
    if not isinstance(old, str) or not old:
        raise ValueError("old must be a non-empty string")
    if not isinstance(new, str):
        raise ValueError("new must be a string")

    # 写入前统一 CRLF/LF，避免平台换行差异导致本应匹配的文本找不到。
    return {
        "path": path,
        "old": old.replace("\r\n", "\n"),
        "new": new.replace("\r\n", "\n"),
        "replace_all": replace_all,
    }


def _run(input_data: dict[str, Any], context: ToolContext) -> ToolResult:
    """读取原文件、确认替换是否唯一/允许批量，再安全写回更新内容。"""

    target, error = resolve_for_tool(context, input_data["path"], "write")
    if error is not None:
        return error
    # 路径错误已在上方返回，这里可将类型缩窄为 Path。
    assert target is not None

    content, read_error = read_text_file(target, input_data["path"])
    if read_error is not None:
        return read_error
    # 读取无错误时 content 一定是 UTF-8 文本。
    assert content is not None

    # count 是安全护栏：默认只接受唯一匹配，避免意外修改多个位置。
    replace_all = bool(input_data.get("replace_all", input_data.get("replaceAll", False)))
    matches = content.count(input_data["old"])
    if matches == 0:
        return ToolResult(ok=False, output=f"Text not found in {input_data['path']}")
    if matches > 1 and not replace_all:
        # 多处匹配必须由调用方明确确认批量替换意图。
        return ToolResult(
            ok=False,
            output=f"Found multiple matches in {input_data['path']}; use replace_all=true.",
        )

    # str.replace 的 -1 表示替换全部，1 表示只替换第一个匹配。
    count = -1 if replace_all else 1
    updated = content.replace(input_data["old"], input_data["new"], count)
    # 只有替换规则全部验证通过后才请求审批，避免让用户确认一个不会执行的修改。
    preview = build_diff_preview(input_data["path"], content, updated)
    approval_error = ensure_edit_for_tool(context, target, preview)
    if approval_error is not None:
        return approval_error
    # 精确替换只记录一次原始全文，不为内存中的中间字符串制造伪快照。
    checkpoint_for_tool(context, target, content)
    result = write_text_file(target, input_data["path"], updated)
    # 共享写入函数可能返回磁盘/权限错误，不能假设更新已经落盘。
    if not result.ok:
        return result
    return ToolResult(ok=True, output=f"Edited {input_data['path']}")


# 注册精确替换工具，schema 为模型生成参数提供最小提示。
edit_file_tool = ToolDefinition(
    name="edit_file",
    description="Replace exact text in a UTF-8 file relative to the workspace root.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "old": {"type": "string"},
            "new": {"type": "string"},
            "replace_all": {"type": "boolean"},
        },
        "required": ["path", "old", "new"],
    },
    validator=_validate,
    run=_run,
)
