from __future__ import annotations

# 汇总默认文件工具，并构造供 agent/headless 使用的独立注册表。

from minicode_lite.tooling import ToolRegistry
from minicode_lite.tools.edit_file import edit_file_tool
from minicode_lite.tools.list_files import list_files_tool
from minicode_lite.tools.patch_file import patch_file_tool
from minicode_lite.tools.read_file import read_file_tool
from minicode_lite.tools.run_command import run_command_tool
from minicode_lite.tools.write_file import write_file_tool


def create_default_tool_registry() -> ToolRegistry:
    """按稳定顺序创建包含文件工具和阶段 7 命令工具的全新 ToolRegistry。"""

    return ToolRegistry(
        [
            # 列表顺序同时决定 `/tools` 的展示顺序，便于学习和测试。
            list_files_tool,
            read_file_tool,
            write_file_tool,
            edit_file_tool,
            patch_file_tool,
            run_command_tool,
        ]
    )


# 只导出构造函数和各工具定义，隐藏模块内部的校验/执行辅助函数。
__all__ = [
    "create_default_tool_registry",
    "edit_file_tool",
    "list_files_tool",
    "patch_file_tool",
    "read_file_tool",
    "run_command_tool",
    "write_file_tool",
]
