"""兼容阶段 5 的导入路径；阶段 11 的命令实现统一位于 cli_commands。"""

# 显式转发公开函数，让旧调用方升级后仍能使用相同接口。
from minicode_lite.cli_commands import format_tools, try_handle_local_command


__all__ = ["format_tools", "try_handle_local_command"]
