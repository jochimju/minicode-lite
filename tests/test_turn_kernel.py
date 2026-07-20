from __future__ import annotations

import pytest

from minicode_lite.turn_kernel import (
    TurnRecurrentState,
    decide_assistant_turn,
    decide_tool_turn,
    derive_turn_step_policy,
)


def _policy_at_step(state: TurnRecurrentState):
    state.begin_step()
    return derive_turn_step_policy(state)


def test_phase_moves_from_explore_to_execute_to_verify() -> None:
    state = TurnRecurrentState(max_steps=4)

    first = _policy_at_step(state)
    second = _policy_at_step(state)
    decide_tool_turn(
        turn_state=state,
        tool_name="read_file",
        result_ok=True,
        result_output="source code",
    )
    third = _policy_at_step(state)

    assert first.phase == "explore"
    assert second.phase == "execute"
    assert third.phase == "verify"
    assert third.verification_evidence_ready is True


def test_policy_reports_max_step_boundary() -> None:
    state = TurnRecurrentState(max_steps=1)

    policy = _policy_at_step(state)

    assert state.has_remaining_steps() is False
    assert policy.remaining_steps == 0
    assert policy.allow_widening is True


def test_empty_response_retries_once_then_falls_back() -> None:
    state = TurnRecurrentState(max_steps=3)
    policy = _policy_at_step(state)

    first = decide_assistant_turn(
        turn_state=state,
        step_content="",
        is_progress=False,
        step_policy=policy,
        empty_response_retry_message="retry",
    )
    second = decide_assistant_turn(
        turn_state=state,
        step_content="  ",
        is_progress=False,
        step_policy=policy,
        empty_response_retry_message="retry",
    )

    assert first.kind == "retry"
    assert first.user_content == "retry"
    assert second.kind == "fallback"
    assert second.stop_reason == "empty_response"


def test_verification_guard_rejects_final_without_successful_evidence() -> None:
    state = TurnRecurrentState(max_steps=3)
    decide_tool_turn(
        turn_state=state,
        tool_name="pytest",
        result_ok=False,
        result_output="1 failed",
    )
    policy = _policy_at_step(state)

    decision = decide_assistant_turn(
        turn_state=state,
        step_content="Everything is complete.",
        is_progress=False,
        step_policy=policy,
        empty_response_retry_message="retry",
    )

    assert policy.phase == "verify"
    assert policy.verification_evidence_ready is False
    assert decision.kind == "guard"
    assert "no successful" in (decision.assistant_content or "")


def test_successful_non_empty_tool_result_allows_verified_final() -> None:
    state = TurnRecurrentState(max_steps=3)
    decide_tool_turn(
        turn_state=state,
        tool_name="pytest",
        result_ok=True,
        result_output="5 passed",
    )
    policy = _policy_at_step(state)

    decision = decide_assistant_turn(
        turn_state=state,
        step_content="Tests passed.",
        is_progress=False,
        step_policy=policy,
        empty_response_retry_message="retry",
    )

    assert state.verification_evidence == "5 passed"
    assert decision.kind == "final"


def test_widening_extends_budget_only_once() -> None:
    state = TurnRecurrentState(max_steps=1)
    state.begin_step()

    first = state.activate_widening(extra_steps=1)
    second = state.activate_widening(extra_steps=10)

    assert first is True
    assert second is False
    assert state.max_steps == 2
    assert state.widening_transition_count == 1


def test_invalid_budget_is_rejected() -> None:
    with pytest.raises(ValueError, match="max_steps"):
        TurnRecurrentState(max_steps=-1)
