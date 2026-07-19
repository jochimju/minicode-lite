from __future__ import annotations

# 收敛所有文件工具共享的路径、UTF-8 读取和写入错误处理。

from difflib import unified_diff
from pathlib import Path

from minicode_lite.tooling import ToolContext, ToolResult
from minicode_lite.session import create_file_checkpoint
from minicode_lite.workspace import resolve_tool_path


def resolve_for_tool(context: ToolContext, path: str, mode: str) -> tuple[Path | None, ToolResult | None]:
    """将路径越界异常改写成工具可以直接返回的失败结果。"""

    try:
        # 唯一的路径解析入口，确保每个文件工具使用同一套边界规则。
        return resolve_tool_path(context, path, mode), None
    except PermissionError as error:
        # 工具层不抛出权限错误，交给模型的应是可读的 ToolResult。
        return None, ToolResult(ok=False, output=str(error))


def build_diff_preview(path: str, before: str, after: str, max_chars: int = 4_000) -> str:
    """生成有长度上限的 unified diff，供编辑审批界面快速核对变化。"""

    # splitlines(keepends=True) 保留原换行，使 difflib 输出接近真实补丁格式。
    preview = "".join(
        unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )
    if len(preview) <= max_chars:
        return preview
    # 审批文本只用于理解变化，不应让超大文件挤满模型或终端上下文。
    return f"{preview[:max_chars]}\n... diff preview truncated ..."


def ensure_edit_for_tool(
    context: ToolContext,
    target: Path,
    diff_preview: str,
) -> ToolResult | None:
    """在存在权限管理器时执行编辑审批，并把拒绝转换成工具失败。"""

    if context.permissions is None:
        # 保留阶段 4 的可注入测试方式：没有策略对象时仍由 workspace 默认边界保护。
        return None
    try:
        # 审批必须发生在调用 write_text_file 之前，保证拒绝时磁盘内容完全不变。
        context.permissions.ensure_edit(str(target), diff_preview)
    except PermissionError as error:
        return ToolResult(ok=False, output=str(error))
    return None


def checkpoint_for_tool(
    context: ToolContext,
    target: Path,
    previous_content: str,
) -> None:
    """在审批通过后、真正写盘前记录旧文件状态。"""

    # target 已由 workspace 层规范化；exists 在此刻反映副作用前的真实状态。
    create_file_checkpoint(
        context.session,
        file_path=target,
        existed=target.exists(),
        previous_content=previous_content,
    )


def read_text_file(target: Path, display_path: str) -> tuple[str | None, ToolResult | None]:
    """以 UTF-8 读取文本，并把常见文件系统错误统一转换为 ToolResult。"""

    try:
        # 明确 UTF-8 避免依赖机器默认编码，保证跨环境行为一致。
        content = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        # 不暴露底层 traceback，给模型可操作的“不存在”反馈。
        return None, ToolResult(ok=False, output=f"File not found: {display_path}")
    except IsADirectoryError:
        # 目录不能当作文本文件读取，需要与不存在区分开。
        return None, ToolResult(ok=False, output=f"Path is a directory: {display_path}")
    except UnicodeDecodeError:
        # 解码失败通常意味着二进制内容，避免将乱码送回模型上下文。
        return None, ToolResult(
            ok=False,
            output=f"File {display_path} appears to be binary. Cannot read as UTF-8 text.",
        )
    except OSError as error:
        # 其余操作系统错误同样降级为可显示的工具失败。
        return None, ToolResult(ok=False, output=f"Could not read {display_path}: {error}")

    if "\x00" in content:
        # 有些二进制文件可被 UTF-8 解码；NUL 字符是额外的保守检测信号。
        return None, ToolResult(
            ok=False,
            output=f"File {display_path} appears to be binary. Cannot read as UTF-8 text.",
        )
    # 成功时只返回文本，错误位置用 None 表示不存在失败结果。
    return content, None


def write_text_file(target: Path, display_path: str, content: str) -> ToolResult:
    """创建缺失父目录后以 UTF-8 写入文本，并保持统一结果格式。"""

    try:
        # 写入前创建父目录，使工具可以写入新的嵌套相对路径。
        target.parent.mkdir(parents=True, exist_ok=True)
        # 明确编码与 read_text_file 对称，避免平台默认编码差异。
        target.write_text(content, encoding="utf-8")
    except OSError as error:
        # 磁盘、权限等失败不能让 agent loop 异常退出。
        return ToolResult(ok=False, output=f"Could not write {display_path}: {error}")
    # 成功信息使用用户原始路径，输出更贴近其输入。
    return ToolResult(ok=True, output=f"Wrote {display_path}")
