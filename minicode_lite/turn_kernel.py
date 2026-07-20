from __future__ import annotations

"""把单轮 agent 的状态推进和分支判断集中为可测试的 turn policy。"""

from dataclasses import dataclass
from typing import Literal


# phase 描述当前模型步骤的主要目标，而不是模型内部不可见的思考过程。
TurnStepPhase = Literal["explore", "execute", "verify"]
# stop reason 使用有限集合，便于日志、测试和后续 session 统一解释结束原因。
TurnStopReason = Literal[
    "assistant_final",
    "empty_response",
    "unsupported_step",
    "max_steps",
]


@dataclass(slots=True)
class TurnStepPolicy:
    """某个模型步骤开始时，由累计状态推导出的只读决策快照。"""

    # phase 告诉循环当前更应探索、执行还是基于工具观察做验证收尾。
    phase: TurnStepPhase
    # step_index 是从 1 开始的模型调用序号，便于教学和诊断。
    step_index: int
    # remaining_steps 是当前步骤已经占用预算后还剩多少次模型调用。
    remaining_steps: int
    # requires_verification 表示已有工具行动，final 不能脱离本轮证据。
    requires_verification: bool
    # verification_evidence_ready 表示至少已有一次成功且非空的工具观察。
    verification_evidence_ready: bool
    # allow_widening 只在预算耗尽且尚未扩宽时开放一次额外预算。
    allow_widening: bool
    # widening_active 让调用方看见当前预算是否已经扩宽过。
    widening_active: bool


@dataclass(slots=True)
class TurnRecurrentState:
    """保存一次 turn 跨模型步骤反复使用的最小可变状态。"""

    # max_steps 是当前有效上限；widening 激活后会在这里增加额外预算。
    max_steps: int
    # step 记录已经开始的模型调用次数。
    step: int = 0
    # phase 保留最近一次推导结果，方便日志或测试检查状态迁移。
    phase: TurnStepPhase = "explore"
    # 空响应只允许有限重试，避免模型持续输出空白造成死循环。
    empty_response_retry_limit: int = 1
    empty_response_retry_count: int = 0
    # 工具观察决定 turn 是否已经从纯探索进入验证责任区。
    saw_tool_result: bool = False
    successful_tool_result_count: int = 0
    tool_error_count: int = 0
    # 最近的成功工具输出作为轻量 verification evidence，不保存无限历史。
    verification_evidence: str = ""
    # widening 的布尔值和次数共同防止预算被反复增加。
    widening_active: bool = False
    widening_transition_count: int = 0
    # stop_reason 由循环在真正终止时写入，策略推导本身不伪造结束状态。
    stop_reason: TurnStopReason | None = None

    def __post_init__(self) -> None:
        """尽早拒绝负预算和负重试次数，避免循环边界含糊。"""

        if self.max_steps < 0:
            raise ValueError("max_steps must be greater than or equal to 0")
        if self.empty_response_retry_limit < 0:
            raise ValueError("empty_response_retry_limit must be greater than or equal to 0")

    @property
    def remaining_steps(self) -> int:
        """返回尚未开始的模型步骤数，最小为 0。"""

        return max(self.max_steps - self.step, 0)

    def has_remaining_steps(self) -> bool:
        """循环在开始下一次模型调用前使用这个硬边界。"""

        return self.step < self.max_steps

    def begin_step(self) -> int:
        """占用一次模型预算并返回从 1 开始的步骤序号。"""

        self.step += 1
        return self.step

    def can_retry_empty_response(self) -> bool:
        """判断空响应重试额度是否仍可使用。"""

        return self.empty_response_retry_count < self.empty_response_retry_limit

    def record_empty_response_retry(self) -> None:
        """消费一次空响应重试额度。"""

        self.empty_response_retry_count += 1

    def record_tool_result(self, *, ok: bool, output: str) -> None:
        """把工具结果折叠为验证、错误与 phase 推导所需的最小状态。"""

        self.saw_tool_result = True
        if ok:
            self.successful_tool_result_count += 1
            # 只有成功且非空的观察才能支撑 final；空成功结果仍需继续验证。
            normalized = " ".join(output.split())
            if normalized:
                # 有界摘要避免大型工具输出在控制状态中被复制一遍。
                self.verification_evidence = normalized[:200]
        else:
            # 错误结果说明行动失败，不能被误当成完成任务的正向证据。
            self.tool_error_count += 1

    def has_verification_evidence(self) -> bool:
        """成功工具观察和非空摘要必须同时成立。"""

        return self.successful_tool_result_count > 0 and bool(self.verification_evidence)

    def activate_widening(self, *, extra_steps: int = 1) -> bool:
        """至多一次增加预算；返回值说明本次调用是否真的发生迁移。"""

        if self.widening_active or extra_steps <= 0:
            return False
        self.widening_active = True
        self.widening_transition_count += 1
        self.max_steps += extra_steps
        return True

    def set_stop_reason(self, reason: TurnStopReason) -> None:
        """记录最终停止原因，供 loop 日志和后续 session 治理使用。"""

        self.stop_reason = reason


@dataclass(slots=True)
class AssistantTurnDecision:
    """kernel 对 assistant 步骤给出的结构化处理意见。"""

    kind: Literal["progress", "retry", "guard", "fallback", "final"]
    assistant_content: str | None = None
    user_content: str | None = None
    stop_reason: TurnStopReason | None = None


@dataclass(slots=True)
class ToolTurnDecision:
    """kernel 对单个工具结果给出的结构化处理意见。"""

    kind: Literal["continue"] = "continue"
    progress_summary: str = ""


def derive_turn_step_policy(turn_state: TurnRecurrentState) -> TurnStepPolicy:
    """根据当前累计状态推导本步骤 phase、验证责任和预算信号。"""

    # 一旦有工具结果，下一步首要任务是判断证据是否足以支持最终结论。
    if turn_state.saw_tool_result:
        phase: TurnStepPhase = "verify"
    # 第一个模型步骤用于理解和锚定用户任务。
    elif turn_state.step <= 1:
        phase = "explore"
    else:
        # 尚无外部观察的后续步骤进入 execute，鼓励产生实际行动。
        phase = "execute"

    turn_state.phase = phase
    evidence_ready = turn_state.has_verification_evidence()
    # 当前步骤用完基础预算后，如果还需继续，loop 可消费唯一一次 widening。
    allow_widening = turn_state.remaining_steps == 0 and not turn_state.widening_active
    return TurnStepPolicy(
        phase=phase,
        step_index=turn_state.step,
        remaining_steps=turn_state.remaining_steps,
        requires_verification=turn_state.saw_tool_result,
        verification_evidence_ready=evidence_ready,
        allow_widening=allow_widening,
        widening_active=turn_state.widening_active,
    )


def decide_assistant_turn(
    *,
    turn_state: TurnRecurrentState,
    step_content: str,
    is_progress: bool,
    step_policy: TurnStepPolicy,
    empty_response_retry_message: str,
) -> AssistantTurnDecision:
    """把 assistant 输出归类为进度、重试、验证守卫、final 或失败收束。"""

    if is_progress:
        # progress 只展示过程，不具备结束 turn 的语义。
        return AssistantTurnDecision(kind="progress", assistant_content=step_content)

    if not step_content.strip():
        if turn_state.can_retry_empty_response():
            # 重试计数由 kernel 维护，loop 只负责把 nudge 写入消息历史。
            turn_state.record_empty_response_retry()
            return AssistantTurnDecision(kind="retry", user_content=empty_response_retry_message)
        return AssistantTurnDecision(
            kind="fallback",
            assistant_content="Stopped because the model returned an empty response twice.",
            stop_reason="empty_response",
        )

    if (
        step_policy.phase == "verify"
        and step_policy.requires_verification
        and not step_policy.verification_evidence_ready
    ):
        # 工具失败或空输出后直接声称完成属于过早 final，必须退回模型补验证。
        return AssistantTurnDecision(
            kind="guard",
            assistant_content=(
                "Verification guard: final answer withheld because this turn has no "
                "successful non-empty tool evidence."
            ),
            user_content=(
                "Run one concrete verification step before finalizing, or report the exact blocker."
            ),
        )

    return AssistantTurnDecision(
        kind="final",
        assistant_content=step_content,
        stop_reason="assistant_final",
    )


def decide_tool_turn(
    *,
    turn_state: TurnRecurrentState,
    tool_name: str,
    result_ok: bool,
    result_output: str,
) -> ToolTurnDecision:
    """记录一次工具观察，并让 loop 继续回到模型做验证或收尾。"""

    turn_state.record_tool_result(ok=result_ok, output=result_output)
    status = "succeeded" if result_ok else "failed"
    return ToolTurnDecision(progress_summary=f"{tool_name} {status}")


__all__ = [
    "AssistantTurnDecision",
    "ToolTurnDecision",
    "TurnRecurrentState",
    "TurnStepPhase",
    "TurnStepPolicy",
    "TurnStopReason",
    "decide_assistant_turn",
    "decide_tool_turn",
    "derive_turn_step_policy",
]
