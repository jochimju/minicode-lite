from __future__ import annotations

# 提供确定性的模型替身，让 harness 不连接真实 provider 也能稳定演示和测试。

from collections.abc import Callable, Iterable
from typing import Any

from minicode_lite.types import AgentStep, ChatMessage


def _last_user_message(messages: list[ChatMessage]) -> str:
    """从最新到最旧寻找用户文本；没有用户消息时返回空字符串。"""

    # 反向遍历确保当前 turn 使用最近一次用户意图，而不是过期历史。
    return next(
        (message.get("content", "") for message in reversed(messages) if message.get("role") == "user"),
        "",
    )


def _last_tool_result(messages: list[ChatMessage]) -> ChatMessage | None:
    """取得最近一次工具观察，让 mock 模型能够基于工具输出形成最终回答。"""

    return next(
        (message for message in reversed(messages) if message.get("role") == "tool_result"),
        None,
    )


def _latest_assistant_tool_name(messages: list[ChatMessage]) -> str | None:
    """寻找最近声明的工具名，用于让结果说明更贴合对应调用。"""

    call = next(
        (message for message in reversed(messages) if message.get("role") == "assistant_tool_call"),
        None,
    )
    if call is None:
        # 没有工具调用记录时，调用方可以回退到 tool_result 自带的工具名。
        return None
    return call.get("toolName")


class ScriptedModel:
    """按预设顺序交付 AgentStep，专门用于可重复的 agent loop 测试。"""

    def __init__(self, steps: Iterable[AgentStep]) -> None:
        # 立刻物化 iterable，保证生成器输入也可重复按索引读取。
        self._steps = list(steps)
        # calls 记录已经消费的步骤数，等同于脚本当前游标。
        self.calls = 0
        # 保存每次收到的历史快照，测试可据此验证 loop 传递的消息顺序。
        self.received_messages: list[list[ChatMessage]] = []

    def next(
        self,
        messages: list[ChatMessage],
        on_stream_chunk: Callable[[str], None] | None = None,
        store: Any | None = None,
    ) -> AgentStep:
        """交付下一个预设步骤；脚本耗尽时主动报错暴露测试配置问题。"""

        # 这两个扩展参数只为满足 ModelAdapter 协议，脚本模型不使用它们。
        del on_stream_chunk, store
        # 保存本次输入，便于测试检查模型是否看到了工具结果或重试提示。
        self.received_messages.append(messages)
        if self.calls >= len(self._steps):
            # 不循环复用最后一步，避免测试在意外循环时假装成功。
            raise IndexError(f"ScriptedModel has no step {self.calls + 1}")
        # 先按当前游标取出步骤，再推进游标，保持调用和脚本位置一一对应。
        step = self._steps[self.calls]
        self.calls += 1
        return step


class MockModelAdapter:
    """用少量规则模拟“读文件后总结”与普通文本回答的最小模型行为。"""

    def next(
        self,
        messages: list[ChatMessage],
        on_stream_chunk: Callable[[str], None] | None = None,
        store: Any | None = None,
    ) -> AgentStep:
        """依据最近工具结果或用户消息生成确定性 AgentStep。"""

        # 当前 mock 不实现流式输出或外部存储，但保留协议兼容参数。
        del on_stream_chunk, store
        # 工具结果优先，因为模型在执行工具后应先消化新观察再决定回答。
        tool_result = _last_tool_result(messages)
        if tool_result is not None:
            # 优先使用调用消息的工具名，缺失时才使用结果消息中的冗余名称。
            tool_name = _latest_assistant_tool_name(messages) or tool_result.get("toolName")
            # 缺失内容按空文本处理，使 mock 对不完整历史也保持确定性。
            content = tool_result.get("content", "")
            if tool_name == "read_file":
                # 读文件的专用措辞使 CLI/headless 演示更接近真实 agent 的回答。
                return AgentStep(type="assistant", content=f"File contents:\n\n{content}")
            # 其他工具使用通用回显，仍把外部观察传回用户。
            return AgentStep(type="assistant", content=f"I received the tool result:\n\n{content}")

        # 尚未执行工具时，从最新用户消息判断是否需要调用 read_file。
        user_text = _last_user_message(messages).strip()
        if user_text.startswith("/read "):
            # 去掉命令前缀与两端空白，得到工具所需的纯路径参数。
            path = user_text[len("/read ") :].strip()
            return AgentStep(
                type="tool_calls",
                calls=[
                    {
                        # 固定 ID 足以支撑此最小 mock，真实模型会为每次调用生成唯一 ID。
                        "id": "mock-read-1",
                        "toolName": "read_file",
                        "input": {"path": path},
                    }
                ],
            )

        # 默认分支保证普通 prompt 也能在没有真实 provider 时完成单轮闭环。
        return AgentStep(
            type="assistant",
            content="MiniCode Lite mock model received your message.",
        )
