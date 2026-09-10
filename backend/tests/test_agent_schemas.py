import pytest
from pydantic import ValidationError

from backend.app.agent.schemas import (
    AgentAction,
    AgentPhase,
    AgentStatus,
    AgentTurnResult,
    PlannerDecision,
)


def test_planner_decision_rejects_unknown_action() -> None:
    with pytest.raises(ValidationError):
        PlannerDecision(action="SCORE", reason="越过阶段二边界")


def test_agent_turn_result_serializes_optional_status_without_api_replacement() -> None:
    result = AgentTurnResult(
        decision=PlannerDecision(
            action=AgentAction.FOLLOW_UP,
            target_competency_id="c-1",
            reason="缺少结果证据",
            question_goal="验证可量化结果",
        ),
        current_question={"id": "q-2", "content": "结果如何衡量？"},
        agent_status=AgentStatus(
            phase=AgentPhase.FOLLOWING_UP,
            confirmed_competency_ids=[],
            active_competency_id="c-1",
            pending_evidence=["项目结果"],
            reason="缺少结果证据",
        ),
    )

    assert result.model_dump()["agent_status"]["active_competency_id"] == "c-1"
    assert result.retryable is False
