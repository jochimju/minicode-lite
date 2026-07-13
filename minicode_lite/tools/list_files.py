from __future__ import annotations

# 定义列出工作区目录内容的只读工具。

from pathlib import Path
from typing import Any

from minicode_lite.tooling import ToolContext, ToolDefinition, ToolResult
from minicode_lite.tools._shared import resolve_for_tool


def _validate(input_data: Any) -> dict[str, str]:
    """接受可选路径，并将其规范化为工具执行器总能使用的字典。"""

    if input_data is None:
        # 未指定参数时列出工作区根目录，是最常用的默认行为。
        return {"path": "."}
    if not isinstance(input_data, dict):
        raise ValueError("input must be an object")
    # 路径缺失时同样回退到根目录。
    path = input_data.get("path", ".")
    if not isinstance(path, str) or not path:
        raise ValueError("path must be a string")
    return {"path": path}


def _run(input_data: dict[str, str], context: ToolContext) -> ToolResult:
    """安全解析目标路径，并返回单文件或单层目录列表。"""

    # 先经过统一边界检查，后续 iterdir 不会越过工作区。
    target, error = resolve_for_tool(context, input_data["path"], "list")
    if error is not None:
        return error
    # error 为 None 时 target 必然存在；断言帮助类型检查器理解这一不变量。
    assert target is not None

    if not target.exists():
        return ToolResult(ok=False, output=f"Path does not exist: {input_data['path']}")
    if target.is_file():
        # 用户列出文件时仍给出有意义的单项结果，而不是把它当目录报错。
        return ToolResult(ok=True, output=f"file {Path(input_data['path']).name}")

    try:
        # 按不区分大小写的名称排序，使不同文件系统上的展示更稳定。
        entries = sorted(target.iterdir(), key=lambda entry: entry.name.lower())
    except OSError as error:
        return ToolResult(ok=False, output=f"Could not list {input_data['path']}: {error}")

    if not entries:
        return ToolResult(ok=True, output="(empty)")

    # 每项保留类型前缀，模型/用户无需再次访问磁盘就能区分文件和目录。
    lines = [f"{'dir' if entry.is_dir() else 'file'} {entry.name}" for entry in entries]
    return ToolResult(ok=True, output="\n".join(lines))


# 将校验器和执行器封装为可注册定义，供默认注册表和模型共享。
list_files_tool = ToolDefinition(
    name="list_files",
    description="List files and directories relative to the workspace root.",
    input_schema={
        "type": "object",
        "properties": {"path": {"type": "string"}},
    },
    validator=_validate,
    run=_run,
)
