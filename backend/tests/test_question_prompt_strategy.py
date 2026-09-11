from backend.app.services.assessment_prompts import build_question_prompt


def test_question_prompt_includes_planner_strategy_and_evidence_gap():
    prompt = build_question_prompt(
        [], [], [],
        agent_context={"formal_target": {
            "question_strategy": "RESULT_VERIFY",
            "target_indicator_ids": ["i-result"],
            "expected_evidence": ["结果指标"],
        }},
    )
    assert "RESULT_VERIFY" in prompt
    assert "i-result" in prompt
    assert "结果指标" in prompt
