from __future__ import annotations

"""阶段 15 的兼容入口：把轻量 REPL 暴露为 tty_app 名称。"""

from pathlib import Path
from typing import Iterable, TextIO

from minicode_lite.repl import Repl, run_repl


def run_tty_app(*, cwd: str | Path | None = None, inputs: Iterable[str] | None = None,
                output: TextIO | None = None, model=None, **_unused) -> Repl:
    """运行非全屏交互界面并返回 Repl 实例，方便调用方检查 transcript。"""

    repl = Repl(cwd=cwd, output=output, model=model)
    repl.run(inputs)
    return repl


__all__ = ["Repl", "run_repl", "run_tty_app"]
