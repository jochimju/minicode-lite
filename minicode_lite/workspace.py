from __future__ import annotations

# 集中解析工具路径，确保默认情况下工具不会越过当前工作区。

from pathlib import Path

from minicode_lite.tooling import ToolContext


def resolve_tool_path(context: ToolContext, path: str, mode: str) -> Path:
    """把工具传入的路径规范化，并执行权限检查或默认工作区边界检查。"""

    # resolve() 将 cwd 化为绝对规范路径，作为后续安全比较的唯一基准。
    workspace_root = Path(context.cwd).resolve()
    # 先保留用户给出的路径形态，以便正确识别绝对路径与相对路径。
    candidate = Path(path)
    # 相对路径必须从工作区根开始解释；绝对路径则先保留给权限/边界检查。
    target = candidate if candidate.is_absolute() else workspace_root / candidate
    # 解析 `.`、`..` 和符号链接后，避免用表面路径绕开安全检查。
    normalized = target.resolve()

    if context.permissions is not None:
        # 有权限系统时由更高层策略决定该路径和操作模式是否允许。
        context.permissions.ensure_path_access(str(normalized), mode)
        # 策略已接管边界判断，返回同一份规范化路径供工具使用。
        return normalized

    try:
        # 没有权限系统时，只接受仍位于 workspace_root 之下的规范化路径。
        normalized.relative_to(workspace_root)
    except ValueError as error:
        # relative_to 失败说明路径逃出了工作区，需要拒绝而非继续访问磁盘。
        raise PermissionError(f"Path escapes workspace: {path}") from error

    # 通过检查后返回绝对路径，使后续文件工具不必重复进行路径拼接。
    return normalized
