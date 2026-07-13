from __future__ import annotations

# 定义 `minicode-lite` 的命令行入口，并保留阶段 0 的无参数 smoke 行为。

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from minicode_lite.headless import run_headless


# READY_MESSAGE 让未提供任务时的最小安装验证有稳定可断言的输出。
READY_MESSAGE = "MiniCode Lite ready"


def build_parser() -> argparse.ArgumentParser:
    """构建主 CLI 参数解析器，独立出来以便测试命令行契约。"""

    parser = argparse.ArgumentParser(
        prog="minicode-lite",
        description="MiniCode Lite command line entry point.",
    )
    # 版本查询不应启动模型或工具，因此采用独立布尔开关。
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print the package version and exit.",
    )
    # 剩余位置参数组成一次 headless prompt，兼容 `python -m ... hello world`。
    parser.add_argument(
        "prompt",
        nargs="*",
        help="Prompt to run once in headless mode.",
    )
    return parser


def run(
    argv: Sequence[str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    cwd: str | Path | None = None,
) -> int:
    """处理版本、单轮 prompt 和无参数 smoke 三种 CLI 模式。"""

    parser = build_parser()
    args = parser.parse_args(argv)
    # 测试可传入内存流；真实命令行调用则延迟选择 sys.stdout。
    output = stdout
    if output is None:
        import sys

        output = sys.stdout
    # stderr 同理独立注入，保证错误不会和正常结果混在同一流中。
    error_output = stderr
    if error_output is None:
        import sys

        error_output = sys.stderr

    if args.version:
        # 仅在确实需要时导入版本，保持包元数据的单一来源。
        from minicode_lite import __version__

        # 版本查询成功后立即返回，不继续解析或执行 prompt。
        print(__version__, file=output)
        return 0

    # 将 argparse 收集的词组恢复成用户输入的一次任务文本。
    prompt = " ".join(args.prompt).strip()
    if prompt:
        try:
            # 有任务时复用 headless 实现，避免 CLI 和单轮执行逻辑分叉。
            print(run_headless(prompt, cwd=cwd), file=output)
        except ValueError as error:
            print(f"Error: {error}", file=error_output)
            return 1
        return 0

    # 无参数仍输出阶段 0 的就绪文本，作为安装/入口 smoke 检查。
    print(READY_MESSAGE, file=output)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """供 console script 和 `python -m` 调用的最薄包装层。"""

    return run(argv)
