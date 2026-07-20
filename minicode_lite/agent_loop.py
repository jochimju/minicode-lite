from __future__ import annotations

"""执行模型与工具循环，并把每一步的控制决策委托给 turn kernel。"""

from collections.abc import Callable
from typing import Any

from minicode_lite.logging_config import log_turn_stop
from minicode_lite.tooling import ToolContext, ToolRegistry, ToolResult
from minicode_lite.turn_kernel import (
    TurnRecurrentState,
    decide_assistant_turn,
    decide_tool_turn,
    derive_turn_step_policy,
)
from minicode_lite.types import ChatMessage, ModelAdapter, ToolCall


# 空回答时追加给模型的提示，允许一次可控重试而不是直接失败。
EMPTY_RESPONSE_RETRY_MESSAGE = (
    "Your last response was empty. Please continue with a tool call or a final answer."
)


def _snapshot_messages(messages: list[ChatMessage]) -> list[ChatMessage]:
    """复制消息列表和每条字典，隔离模型或回调对历史的意外修改。"""

    # 浅复制已经足够，因为 loop 不会改写消息中的嵌套工具输入。
    return [dict(message) for message in messages]


def _append_assistant_message(
    messages: list[ChatMessage],
    content: str,
    on_assistant_message: Callable[[str], None] | None,
) -> None:
    """记录最终 assistant 文本，并在需要时通知展示层。"""

    messages.append({"role": "assistant", "content": content})
    if on_assistant_message is not None:
        # 回调是可选 UI 钩子，核心循环不依赖具体界面。
        on_assistant_message(content)


def _append_progress_message(
    messages: list[ChatMessage],
    content: str,
    on_progress_message: Callable[[str], None] | None,
) -> None:
    """把非终止性 assistant 信息写入独立进度通道。"""

    if not content:
        return
    messages.append({"role": "assistant_progress", "content": content})
    if on_progress_message is not None:
        on_progress_message(content)


def _append_tool_call_message(messages: list[ChatMessage], call: ToolCall) -> None:
    """把模型提出的工具意图写入历史，供结果按调用 ID 配对。"""

    messages.append(
        {
            "role": "assistant_tool_call",
            "content": "",
            "toolUseId": call["id"],
            "toolName": call["toolName"],
            "input": call["input"],
        }
    )


def _append_tool_result_message(
    messages: list[ChatMessage],
    call: ToolCall,
    result: ToolResult,
) -> None:
    """把工具观察编码成模型下一步能够读取的历史消息。"""

    messages.append(
        {
            "role": "tool_result",
            "content": result.output,
            "toolUseId": call["id"],
            "toolName": call["toolName"],
            "isError": not result.ok,
        }
    )


def _widen_if_needed(
    turn_state: TurnRecurrentState,
    *,
    widening_extra_steps: int,
) -> None:
    """当当前决策必须继续但预算耗尽时，尝试唯一一次预算扩宽。"""

    if not turn_state.has_remaining_steps():
        # activate_widening 自带幂等保护，重复到达边界不会无限增加预算。
        turn_state.activate_widening(extra_steps=widening_extra_steps)


def _run_agent_turn_impl(
    *,
    model: ModelAdapter,
    tools: ToolRegistry,
    messages: list[ChatMessage],
    cwd: str,
    max_steps: int = 8,
    widening_extra_steps: int = 1,
    permissions: Any | None = None,
    session: Any | None = None,
    runtime: dict[str, Any] | None = None,
    store: Any | None = None,
    on_tool_start: Callable[[str, Any], None] | None = None,
    on_tool_result: Callable[[str, str, bool], None] | None = None,
    on_assistant_message: Callable[[str], None] | None = None,
    on_progress_message: Callable[[str], None] | None = None,
) -> list[ChatMessage]:
    """执行一轮有限 agent 交互，返回包含本轮新增记录的历史副本。"""

    # 调用者传入的历史保持不变；本轮只修改工作副本。
    working_messages = _snapshot_messages(messages)
    # recurrent state 是 loop 与 policy 之间唯一的单轮控制状态。
    turn_state = TurnRecurrentState(max_steps=max_steps)

    while turn_state.has_remaining_steps():
        # 先占用预算再推导策略，让 remaining_steps 表示本次之后还能调用几次模型。
        step_index = turn_state.begin_step()
        step_policy = derive_turn_step_policy(turn_state)
        # 模型只收到历史副本，不能篡改 loop 维护的权威记录。
        next_step = model.next(_snapshot_messages(working_messages), store=store)

        if next_step.type == "assistant":
            decision = decide_assistant_turn(
                turn_state=turn_state,
                step_content=next_step.content,
                is_progress=(
                    next_step.kind == "progress" or next_step.contentKind == "progress"
                ),
                step_policy=step_policy,
                empty_response_retry_message=EMPTY_RESPONSE_RETRY_MESSAGE,
            )
            if decision.kind == "progress":
                _append_progress_message(
                    working_messages,
                    decision.assistant_content or "",
                    on_progress_message,
                )
                _widen_if_needed(
                    turn_state,
                    widening_extra_steps=widening_extra_steps,
                )
                continue

            if decision.kind == "retry":
                # 重试 nudge 作为用户消息进入上下文，模型才能看见格式纠正要求。
                working_messages.append(
                    {"role": "user", "content": decision.user_content or ""}
                )
                _widen_if_needed(
                    turn_state,
                    widening_extra_steps=widening_extra_steps,
                )
                continue

            if decision.kind == "guard":
                # 守卫说明对用户可见，但不会伪装成最终回答。
                _append_progress_message(
                    working_messages,
                    decision.assistant_content or "",
                    on_progress_message,
                )
                if decision.user_content:
                    working_messages.append(
                        {"role": "user", "content": decision.user_content}
                    )
                _widen_if_needed(
                    turn_state,
                    widening_extra_steps=widening_extra_steps,
                )
                continue

            if decision.kind == "fallback":
                _append_assistant_message(
                    working_messages,
                    decision.assistant_content or "The turn was stopped.",
                    on_assistant_message,
                )
                turn_state.set_stop_reason(decision.stop_reason or "empty_response")
                log_turn_stop(turn_state.stop_reason, steps=step_index)
                return working_messages

            # 只有 kernel 判定为 final 的文本才能终止本轮。
            _append_assistant_message(
                working_messages,
                decision.assistant_content or "",
                on_assistant_message,
            )
            turn_state.set_stop_reason(decision.stop_reason or "assistant_final")
            log_turn_stop(turn_state.stop_reason, steps=step_index)
            return working_messages

        if next_step.type == "tool_calls":
            # 同一模型步骤中的调用先完整记录意图，再按顺序执行结果。
            for call in next_step.calls:
                _append_tool_call_message(working_messages, call)

            for call in next_step.calls:
                if on_tool_start is not None:
                    on_tool_start(call["toolName"], call["input"])
                # registry 负责参数校验、异常隔离和权限边界。
                result = tools.execute(
                    call["toolName"],
                    call["input"],
                    ToolContext(
                        cwd=cwd,
                        permissions=permissions,
                        session=session,
                        runtime=runtime,
                    ),
                )
                if on_tool_result is not None:
                    on_tool_result(call["toolName"], result.output, not result.ok)
                _append_tool_result_message(working_messages, call, result)
                # kernel 只折叠控制状态，不接管真实工具执行或消息序列化。
                decide_tool_turn(
                    turn_state=turn_state,
                    tool_name=call["toolName"],
                    result_ok=result.ok,
                    result_output=result.output,
                )

            # 工具观察之后必须回到模型验证；边界处可补唯一一次预算。
            _widen_if_needed(
                turn_state,
                widening_extra_steps=widening_extra_steps,
            )
            continue

        # 类型约束之外的适配器输出使用明确失败消息安全收束。
        _append_assistant_message(
            working_messages,
            f"Stopped because the model returned an unsupported step type: {next_step.type}",
            on_assistant_message,
        )
        turn_state.set_stop_reason("unsupported_step")
        log_turn_stop("unsupported_step", steps=step_index)
        return working_messages

    # widening 未启用或已消费后仍无 final，使用有效上限报告硬停止原因。
    _append_assistant_message(
        working_messages,
        f"Stopped after reaching max_steps={turn_state.max_steps}.",
        on_assistant_message,
    )
    turn_state.set_stop_reason("max_steps")
    log_turn_stop("max_steps", steps=turn_state.step)
    return working_messages


def run_agent_turn(
    *,
    model: ModelAdapter,
    tools: ToolRegistry,
    messages: list[ChatMessage],
    cwd: str,
    max_steps: int = 8,
    widening_extra_steps: int = 1,
    permissions: Any | None = None,
    session: Any | None = None,
    runtime: dict[str, Any] | None = None,
    store: Any | None = None,
    on_tool_start: Callable[[str, Any], None] | None = None,
    on_tool_result: Callable[[str, str, bool], None] | None = None,
    on_assistant_message: Callable[[str], None] | None = None,
    on_progress_message: Callable[[str], None] | None = None,
) -> list[ChatMessage]:
    """建立 turn 级权限生命周期，再执行受 kernel 管理的 agent loop。"""

    # PermissionManager 是可选扩展；仅在对象提供生命周期方法时调用。
    begin_turn = getattr(permissions, "begin_turn", None)
    end_turn = getattr(permissions, "end_turn", None)
    if callable(begin_turn):
        begin_turn()
    try:
        # finally 保证模型或回调异常时也不会把临时授权泄漏到下一轮。
        return _run_agent_turn_impl(
            model=model,
            tools=tools,
            messages=messages,
            cwd=cwd,
            max_steps=max_steps,
            widening_extra_steps=widening_extra_steps,
            permissions=permissions,
            session=session,
            runtime=runtime,
            store=store,
            on_tool_start=on_tool_start,
            on_tool_result=on_tool_result,
            on_assistant_message=on_assistant_message,
            on_progress_message=on_progress_message,
        )
    finally:
        if callable(end_turn):
            end_turn()
