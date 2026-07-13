"""MiniCode Lite 学习型 harness 包；这里只维护公开版本元数据。"""

# 限制 `from minicode_lite import *` 的公开表面，避免意外导出内部模块名。
__all__ = ["__version__"]

# CLI 的 `--version` 从包的单一版本来源读取该常量。
__version__ = "0.0.1"
