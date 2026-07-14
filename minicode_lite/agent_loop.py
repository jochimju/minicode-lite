from __future__ import annotations

# 实现最小 agent loop：模型决定下一步，工具产生观察，再回到模型得到最终回答。

from collections.abc import Callable
from typing import Any

from minicode_lite.tooling import ToolContext, ToolRegistry, ToolResult
from minicode_lite.types import ChatMessage, ModelAdapter, ToolCall


# 空回答时追加给模型的提示，允许一次可控重试而不是直接失败。
EMPTY_RESPONSE_RETRY_MESSAGE = (
    "Your last response was empty. Please continue with a tool call or a final answer."
)


def _snapshot_messages(messages: list[ChatMessage]) -> list[ChatMessage]:
    """复制消息列表和每条字典，隔离模型/回调对历史的意外修改。"""

    # 浅复制每条消息已经足够，因为当前消息的可变嵌套输入不会在 loop 内改写。
    return [dict(message) for message in messages]


def _append_assistant_message(
    messages: list[ChatMessage],
    content: str,
    on_assistant_message: Callable[[str], None] | None,
) -> None:
    """记录最终 assistant 文本，并在需要时通知展示层。"""

    # 最终回答要进入历史，供调用者提取和后续阶段持久化。
    messages.append({"role": "assistant", "content": content})
    if on_assistant_message is not None:
        # 回调是可选的 UI 钩子，核心 loop 不依赖具体展示界面。
        on_assistant_message(content)


def _append_tool_call_message(messages: list[ChatMessage], call: ToolCall) -> None:
    """把模型提出的工具调用写入历史，供工具结果和模型后续回答关联。"""

    messages.append(
        {
            # 此角色代表模型尚未执行但已经声明的工具意图。
            "role": "assistant_tool_call",
            # 调用本身没有自然语言回答，因此内容保持为空。
            "content": "",
            # 保留调用 ID，后续 result 使用同一 ID 配对。
            "toolUseId": call["id"],
            # 保存名称和输入，使整个历史自描述。
            "toolName": call["toolName"],
            "input": call["input"],
        }
    )


def _append_tool_result_message(
    messages: list[ChatMessage],
    call: ToolCall,
    result: ToolResult,
) -> None:
    """把一次工具运行结果编码成模型下一次能读取的消息。"""

    messages.append(
        {
            # tool_result 是模型观察外部世界、决定下一步行动的依据。
            "role": "tool_result",
            # 工具输出以文本形式进入上下文。
            "content": result.output,
            # 用相同 ID 将观察归属到对应调用。
            "toolUseId": call["id"],
            # 工具名便于 provider/调试器不扫描更早消息也能识别来源。
            "toolName": call["toolName"],
            # ToolResult 的成功标志在消息中反向表示错误状态。
            "isError": not result.ok,
        }
    )


def run_agent_turn(
    *,
    model: ModelAdapter,
    tools: ToolRegistry,
    messages: list[ChatMessage],
    cwd: str,
    max_steps: int = 8,
    permissions: Any | None = None,
    session: Any | None = None,
    runtime: dict[str, Any] | None = None,
    store: Any | None = None,
    on_tool_start: Callable[[str, Any], None] | None = None,
    on_tool_result: Callable[[str, str, bool], None] | None = None,
    on_assistant_message: Callable[[str], None] | None = None,
    on_progress_message: Callable[[str], None] | None = None,
) -> list[ChatMessage]:
    """执行一轮有限步数的 agent 交互，返回新增内容后的消息历史副本。"""

    # 调用者传入的历史不可变；本轮所有状态追加到独立工作副本。
    working_messages = _snapshot_messages(messages)
    # 只允许空响应重试一次，防止模型持续空输出造成无意义循环。
    empty_response_retried = False

    for _step_index in range(max_steps):
        # 每次给模型快照，使适配器无法篡改 loop 的权威消息历史。
        next_step = model.next(
            _snapshot_messages(working_messages),
            store=store,
        )

        if next_step.type == "assistant":
            # assistant 步骤可能是进度提示，也可能是真正终止本轮的最终回答。
            content = next_step.content
            if next_step.kind == "progress" or next_step.contentKind == "progress":
                if content:
                    # 进度信息可见但不终止循环，因此采用独立角色写入历史。
                    working_messages.append({"role": "assistant_progress", "content": content})
                    if on_progress_message is not None:
                        # UI 可选择即时展示进度，而无需理解 AgentStep。
                        on_progress_message(content)
                # 无论进度是否为空，都继续请求模型产生下一步。
                continue

            if not content.strip():
                if empty_response_retried:
                    # 连续第二次空回答时用明确停止消息收束本轮，避免死循环。
                    _append_assistant_message(
                        working_messages,
                        "Stopped because the model returned an empty response twice.",
                        on_assistant_message,
                    )
                    return working_messages
                # 首次空回答时插入一条用户提示，给模型一次纠正格式的机会。
                empty_response_retried = True
                working_messages.append({"role": "user", "content": EMPTY_RESPONSE_RETRY_MESSAGE})
                continue

            # 非空最终文本完成本轮，写入历史并通知可选展示层。
            _append_assistant_message(working_messages, content, on_assistant_message)
            return working_messages

        if next_step.type == "tool_calls":
            # 一个模型步骤中的所有调用同属同一轮决策，必须先完整写入意图批次，
            # 才能让后续 provider 适配器把它们还原为一个 assistant/tool_calls 消息。
            for call in next_step.calls:
                _append_tool_call_message(working_messages, call)

            for call in next_step.calls:
                if on_tool_start is not None:
                    # 工具启动回调支持 CLI/TUI 等产品层展示生命周期。
                    on_tool_start(call["toolName"], call["input"])

                # 注册表负责执行、校验和错误隔离；上下文携带本轮所需环境。
                result = tools.execute(
                    call["toolName"],
                    call["input"],
                    ToolContext(
                        # cwd 是文件工具建立相对路径和安全边界的基准。
                        cwd=cwd,
                        permissions=permissions,
                        session=session,
                        runtime=runtime,
                    ),
                )

                if on_tool_result is not None:
                    # 回调接收已格式化输出和错误标记，展示层无需依赖 ToolResult。
                    on_tool_result(call["toolName"], result.output, not result.ok)
                # 结果写回历史，使下一次 model.next 能根据观察继续推理。
                _append_tool_result_message(working_messages, call, result)
            # 一批工具都执行完后仍需回到模型，不能在此处当作最终回答。
            continue

        # 理论上类型约束已限制分支；此保护分支让异常适配器输出也能安全停止。
        _append_assistant_message(
            working_messages,
            f"Stopped because the model returned an unsupported step type: {next_step.type}",
            on_assistant_message,
        )
        return working_messages

    # 循环耗尽预算仍无最终回答时，显式写入原因，避免静默返回半截历史。
    _append_assistant_message(
        working_messages,
        f"Stopped after reaching max_steps={max_steps}.",
        on_assistant_message,
    )
    return working_messages
