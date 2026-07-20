from __future__ import annotations

"""记录工具 start/result 事件，确保 transcript 不留下悬挂的 running 工具。"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class TranscriptEntry:
    """REPL 展示层的最小事件记录。"""

    kind: str
    body: str = ""
    tool_name: str = ""
    tool_use_id: str = ""
    is_error: bool = False
    state: str = "complete"


@dataclass(slots=True)
class ToolLifecycle:
    """维护工具调用从 running 到 complete/error 的状态转换。"""

    entries: list[TranscriptEntry] = field(default_factory=list)
    _running: dict[str, TranscriptEntry] = field(default_factory=dict)

    def start(self, tool_name: str, tool_use_id: str, tool_input: Any = None) -> TranscriptEntry:
        """追加 running 事件；ID 重复时先关闭旧事件，避免永久悬挂。"""

        if tool_use_id in self._running:
            # 同一 ID 再次 start 表示协议异常；旧事件必须先失败，不能被新事件静默覆盖。
            self._running[tool_use_id].state = "error"
            self._running[tool_use_id].is_error = True
        # start 事件立即进入 entries，使用户能在耗时工具完成前看到正在执行什么。
        entry = TranscriptEntry(
            kind="tool_start",
            body="" if tool_input is None else str(tool_input),
            tool_name=tool_name,
            tool_use_id=tool_use_id,
            state="running",
        )
        self.entries.append(entry)
        # running 索引只保存尚未收到结果的事件，用 ID 保证结果可以精确配对。
        self._running[tool_use_id] = entry
        return entry

    def result(self, tool_name: str, tool_use_id: str, output: str, is_error: bool = False) -> TranscriptEntry:
        """将对应 start 标记完成，并追加可显示的 result 事件。"""

        running = self._running.pop(tool_use_id, None)
        if running is None:
            # provider 异常时可能只有结果；仍保留可回放的错误事实。
            is_error = True
        elif running.tool_name != tool_name:
            is_error = True
            running.is_error = True
            running.state = "error"
        else:
            # start 事件自身也要结束 running 状态，便于折叠视图直接显示最终状态。
            running.is_error = is_error
            running.state = "error" if is_error else "complete"
        entry = TranscriptEntry(
            kind="tool_result",
            body=str(output),
            tool_name=tool_name,
            tool_use_id=tool_use_id,
            is_error=is_error,
        )
        # result 独立追加而不是覆盖 start，transcript 才能还原完整时间顺序。
        self.entries.append(entry)
        return entry

    def finalize(self) -> int:
        """把 turn 结束时仍 running 的工具标成错误，返回受影响数量。"""

        dangling = list(self._running.values())
        for entry in dangling:
            # 退出或异常中断时，running 不再可能自然完成，因此统一收敛为 error。
            entry.state = "error"
            entry.is_error = True
            entry.body = entry.body or "tool did not produce a result"
        # 清空索引确保 finalize 幂等；重复调用不会再次报告同一批工具。
        self._running.clear()
        return len(dangling)

    @property
    def running(self) -> tuple[TranscriptEntry, ...]:
        """只读暴露当前悬挂工具，便于 UI 或测试诊断。"""

        return tuple(self._running.values())
