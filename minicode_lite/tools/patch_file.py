from __future__ import annotations

# 定义多段精确文本替换工具，用一个调用完成有序补丁应用。

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
    """验证补丁列表，并把每一段替换规范为统一的内部结构。"""

    if not isinstance(input_data, dict):
        raise ValueError("input must be an object")
    path = input_data.get("path")
    replacements = input_data.get("replacements")
    if not isinstance(path, str) or not path:
        raise ValueError("path is required")
    if not isinstance(replacements, list) or not replacements:
        raise ValueError("replacements must be a non-empty list")

    # 逐项规范化后，执行器不必再关心字段别名或输入形状。
    normalized = []
    for replacement in replacements:
        if not isinstance(replacement, dict):
            raise ValueError("replacement entries must be objects")
        # 兼容与 edit_file 相同的 old/search、new/replace 字段别名。
        old = replacement.get("old", replacement.get("search"))
        new = replacement.get("new", replacement.get("replace"))
        replace_all = bool(replacement.get("replace_all", replacement.get("replaceAll", False)))
        if not isinstance(old, str) or not old:
            raise ValueError("replacement old must be a non-empty string")
        if not isinstance(new, str):
            raise ValueError("replacement new must be a string")
        # 统一换行符，确保补丁在 Windows 和 Unix 风格文本中一致匹配。
        normalized.append(
            {
                "old": old.replace("\r\n", "\n"),
                "new": new.replace("\r\n", "\n"),
                "replace_all": replace_all,
            }
        )

    return {"path": path, "replacements": normalized}


def _run(input_data: dict[str, Any], context: ToolContext) -> ToolResult:
    """按输入顺序应用每段替换；任一段找不到时停止且不写回文件。"""

    target, error = resolve_for_tool(context, input_data["path"], "write")
    if error is not None:
        return error
    # 成功通过路径检查后，可以安全执行后续文件操作。
    assert target is not None

    content, read_error = read_text_file(target, input_data["path"])
    if read_error is not None:
        return read_error
    # 共享读取成功时内容一定存在。
    assert content is not None

    # 保存原始内容，全部替换完成后用它生成一次整体 diff。
    original_content = content
    applied = 0
    for index, replacement in enumerate(input_data["replacements"], start=1):
        # 按顺序在最新 content 上查找，使后一段可依赖前一段的变换结果。
        if replacement["old"] not in content:
            return ToolResult(
                ok=False,
                output=f"Replacement {index} not found in {input_data['path']}",
            )
        # 与 edit_file 保持相同的单次/全部替换语义。
        replace_all = bool(replacement.get("replace_all", replacement.get("replaceAll", False)))
        count = -1 if replace_all else 1
        content = content.replace(replacement["old"], replacement["new"], count)
        applied += 1

    # 全部补丁成功后先审批整体差异，再只写盘一次，避免半成品修改落到磁盘。
    preview = build_diff_preview(input_data["path"], original_content, content)
    approval_error = ensure_edit_for_tool(context, target, preview)
    if approval_error is not None:
        return approval_error
    # 多段 replacement 是一次原子工具意图，共享一个写前快照即可完整恢复。
    checkpoint_for_tool(context, target, original_content)
    result = write_text_file(target, input_data["path"], content)
    if not result.ok:
        return result
    return ToolResult(
        ok=True,
        output=f"Patched {input_data['path']} with {applied} replacement(s)",
    )


# 注册多段补丁工具，让模型可以在一个 ToolCall 中描述一组有序变更。
patch_file_tool = ToolDefinition(
    name="patch_file",
    description="Apply multiple exact-text replacements to a UTF-8 file.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "replacements": {"type": "array"},
        },
        "required": ["path", "replacements"],
    },
    validator=_validate,
    run=_run,
)
