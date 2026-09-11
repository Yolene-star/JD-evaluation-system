from backend.app.agent.schemas import AgentAction, PlannerDecision


def test_planner_decision_carries_question_strategy_and_target_indicators():
    decision = PlannerDecision(
        action=AgentAction.FOLLOW_UP,
        reason="缺少结果",
        target_competency_id="c1",
        question_strategy="RESULT_VERIFY",
        target_indicator_ids=["i1"],
        expected_evidence=["结果指标"],
    )
    assert decision.question_strategy == "RESULT_VERIFY"
    assert decision.target_indicator_ids == ["i1"]
