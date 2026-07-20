from __future__ import annotations

"""把一行终端输入分成退出、本地命令和 agent 任务三类。"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class InputEvent:
    """输入事件；text 保留去掉首尾空白后的原始任务。"""

    kind: Literal["exit", "local", "agent", "empty"]
    text: str = ""


def classify_input(text: str) -> InputEvent:
    """分类单行输入，避免 REPL 主循环混入字符串判断细节。"""

    # 统一去除边界空白，避免 `/exit ` 和普通任务尾部空格产生不同语义。
    value = text.strip()
    if not value:
        # 空输入不进入本地命令或模型，防止无意义 turn。
        return InputEvent("empty")
    if value in {"/exit", "/quit", "/q"}:
        # 多个常用别名都归一为 exit，主循环无需知道具体拼写。
        return InputEvent("exit", value)
    if value.startswith("/"):
        # 是否为“已知命令”由命令处理器判断；解析层只负责识别本地命令候选。
        return InputEvent("local", value)
    # 其余非空文本保留为自然语言任务，交给 agent loop。
    return InputEvent("agent", value)


def parse_input(text: str) -> InputEvent:
    """兼容更直观的解析命名，返回与 classify_input 相同的事件。"""

    return classify_input(text)
