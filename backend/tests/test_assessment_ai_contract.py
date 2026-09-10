from types import SimpleNamespace

import pytest

from backend.app.models import EvidenceType
from backend.app.services.assessment_ai import (
    AnalysisResult,
    EvidenceResult,
    GeneratedQuestion,
    InvalidAIResponse,
    validate_analysis,
    validate_source_excerpt,
    generate_main_question,
    analyze_answer,
    RetryableAIError,
)
from backend.app.services.assessment_contracts import ConfirmedCompetency, ConfirmedModelSnapshot
from backend.app.agent.schemas import ResumeReference


def valid_result(**changes: object) -> AnalysisResult:
    values = {
        "answer_summary": "回答提到容量评估",
        "evidence": [
            EvidenceResult(
                competency_id="c1",
                type=EvidenceType.POSITIVE,
                excerpt="容量评估",
                summary="有相关实践",
                confidence=0.8,
            )
        ],
        "evidence_sufficiency": "SUFFICIENT",
        "needs_follow_up": False,
        "follow_up_reason": "",
        "follow_up_question": "",
    }
    values.update(changes)
    return AnalysisResult.model_validate(values)


def test_source_excerpt_matches_after_whitespace_normalization() -> None:
    assert validate_source_excerpt("我做过容量 评估。", "容量\n评估")
    assert not validate_source_excerpt("我做过容量评估。", "不存在")


def test_excerpt_not_in_answer_is_downgraded_to_uncertain() -> None:
    result = validate_analysis(valid_result(evidence=[EvidenceResult(competency_id="c1", type=EvidenceType.POSITIVE, excerpt="不存在", summary="", confidence=0.8)]), "用户回答原文", "c1")
    assert result.evidence[0].type == EvidenceType.UNCERTAIN


def test_confidence_out_of_range_is_rejected() -> None:
    with pytest.raises(InvalidAIResponse):
        validate_analysis({**valid_result().model_dump(), "evidence": [{"competency_id": "c1", "type": "POSITIVE", "excerpt": "回答", "summary": "", "confidence": 1.2}]}, "回答", "c1")


def test_cross_competency_evidence_is_rejected() -> None:
    with pytest.raises(InvalidAIResponse):
        validate_analysis(valid_result(evidence=[EvidenceResult(competency_id="c2", type=EvidenceType.POSITIVE, excerpt="回答", summary="", confidence=0.8)]), "回答", "c1")


def test_follow_up_requires_reason_and_question() -> None:
    with pytest.raises(InvalidAIResponse):
        validate_analysis({**valid_result().model_dump(), "needs_follow_up": True, "follow_up_reason": "", "follow_up_question": ""}, "回答", "c1")


def test_generated_question_limits_scope_to_three_ids() -> None:
    question = GeneratedQuestion(content="请描述一次项目经历", covered_competency_ids=["c1", "c2", "c3"], turn_type="MAIN_QUESTION")
    assert question.covered_competency_ids == ["c1", "c2", "c3"]
    with pytest.raises(ValueError):
        GeneratedQuestion(content="问题", covered_competency_ids=[], turn_type="MAIN_QUESTION")
    with pytest.raises(ValueError):
        GeneratedQuestion(content="问题", covered_competency_ids=["c1", "c2", "c3", "c4"], turn_type="MAIN_QUESTION")
    with pytest.raises(ValueError):
        GeneratedQuestion(content="问题", covered_competency_ids=["c1"], background_reference={"source_type": "BACKGROUND_ONLY", "item_id": "r1", "item_type": "resume", "display_summary": "背景"})


def test_main_question_transport_receives_grounded_context(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.services.assessment_ai.get_llm_api_key", lambda: "test-key")
    snapshot = ConfirmedModelSnapshot("m1", "p1", "v1.0", (ConfirmedCompetency("c1", "系统设计", "设计可靠系统", 1.0, ("jd-e1",)),))
    captured = {}
    def transport(payload, **_kwargs):
        captured.update(payload)
        return {"choices": [{"message": {"content": '{"content":"请举例","covered_competency_ids":["c1"],"turn_type":"MAIN_QUESTION"}'}}]}
    result = generate_main_question(
        snapshot,
        list(snapshot.competencies),
        [{"id": "jd-e1", "excerpt": "负责系统设计"}],
        [{"role": "USER", "content": "历史回答"}],
        transport,
        agent_context={
            "current_competency_state": {"status": "FOLLOW_UP"},
            "existing_evidence": [{"summary": "已有设计证据"}],
            "missing_information": ["缺少容量结果"],
            "historical_questions": ["之前的问题"],
        },
    )
    assert result.turn_type == "MAIN_QUESTION"
    user_context = captured["messages"][1]["content"]
    assert "系统设计" in user_context
    assert "负责系统设计" in user_context
    assert "current_competency_state" in user_context
    assert "已有设计证据" in user_context
    assert "缺少容量结果" in user_context
    assert "之前的问题" in user_context
    assert result.evaluation_target is None
    assert result.expected_evidence == []


def test_main_question_personalization_is_background_only_and_formal_target_is_frozen(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.services.assessment_ai.get_llm_api_key", lambda: "test-key")
    snapshot = ConfirmedModelSnapshot("m1", "p1", "v1.0", (ConfirmedCompetency("c1", "系统设计", "", 1.0, ()),))
    reference = ResumeReference(item_id="r1", item_type="project", prompt_hint="候选人背景提到 React 项目，请邀请其确认贡献。")
    formal = {"question_goal": "补充系统设计的具体做法、依据和结果", "expected_evidence": ["本人行动", "可验证结果"]}

    def transport(payload, **_kwargs):
        assert "BACKGROUND_ONLY" in payload["messages"][0]["content"]
        assert "不可改变正式评估目标" in payload["messages"][0]["content"]
        assert "prompt_hint" in payload["messages"][1]["content"]
        return {"choices": [{"message": {"content": '{"content":"请确认 React 项目中的系统设计贡献","covered_competency_ids":["c1"],"turn_type":"MAIN_QUESTION","evaluation_target":"补充系统设计的具体做法、依据和结果","expected_evidence":["本人行动","可验证结果"],"background_reference":{"source_type":"BACKGROUND_ONLY","item_id":"r1","item_type":"project","display_summary":"React 项目"}}'}}]}

    result = generate_main_question(snapshot, list(snapshot.competencies), [], [], transport, agent_context={"formal_target": formal}, resume_reference=reference)
    assert result.background_reference["item_id"] == "r1"
    assert result.evaluation_target == formal["question_goal"]


def test_main_question_rejects_resume_only_target_and_formal_target_mutation(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.services.assessment_ai.get_llm_api_key", lambda: "test-key")
    snapshot = ConfirmedModelSnapshot("m1", "p1", "v1.0", (ConfirmedCompetency("c1", "系统设计", "", 1.0, ()),))
    reference = ResumeReference(item_id="r1", item_type="project", prompt_hint="候选人背景项目")

    def transport(payload, **_kwargs):
        return {"choices": [{"message": {"content": '{"content":"请介绍 React","covered_competency_ids":["resume-only"],"turn_type":"MAIN_QUESTION","evaluation_target":"评估 React","expected_evidence":[]}'}}]}

    with pytest.raises(InvalidAIResponse):
        generate_main_question(snapshot, list(snapshot.competencies), [], [], transport, agent_context={"formal_target": {"question_goal": "评估系统设计", "expected_evidence": ["结果"]}}, resume_reference=reference)


def test_main_question_rejects_competency_outside_snapshot(monkeypatch) -> None:
    snapshot = ConfirmedModelSnapshot("m1", "p1", "v1.0", (ConfirmedCompetency("c1", "系统设计", "", 1.0, ()),))
    with pytest.raises(InvalidAIResponse):
        generate_main_question(snapshot, [ConfirmedCompetency("other", "越权", "", 1.0, ())], [], [], lambda *_args, **_kwargs: {})


def test_main_question_personalization_is_background_only_and_formal_target_is_frozen(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.services.assessment_ai.get_llm_api_key", lambda: "test-key")
    snapshot = ConfirmedModelSnapshot("m1", "p1", "v1.0", (ConfirmedCompetency("c1", "系统设计", "", 1.0, ()),))
    reference = ResumeReference(item_id="r1", item_type="project", prompt_hint="候选人背景提到 React 项目，请邀请其确认贡献。")

    def transport(payload, **_kwargs):
        return {"choices": [{"message": {"content": '{"content":"请确认项目中的系统设计贡献","covered_competency_ids":["c1"],"turn_type":"MAIN_QUESTION","evaluation_target":"评估 React","expected_evidence":[]}'}}]}

    with pytest.raises(InvalidAIResponse):
        generate_main_question(snapshot, list(snapshot.competencies), [], [], transport, agent_context={"formal_target": {"question_goal": "评估系统设计", "expected_evidence": ["结果"]}}, resume_reference=reference)


def test_main_question_rejects_fabricated_background_without_reference(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.services.assessment_ai.get_llm_api_key", lambda: "test-key")
    snapshot = ConfirmedModelSnapshot("m1", "p1", "v1.0", (ConfirmedCompetency("c1", "系统设计", "", 1.0, ()),))

    def transport(payload, **_kwargs):
        return {"choices": [{"message": {"content": '{"content":"请举例","covered_competency_ids":["c1"],"turn_type":"MAIN_QUESTION","background_reference":{"source_type":"BACKGROUND_ONLY","item_id":"r1","item_type":"project","display_summary":"伪造背景"}}'}}]}

    with pytest.raises(InvalidAIResponse):
        generate_main_question(snapshot, list(snapshot.competencies), [], [], transport)


def test_resume_hint_is_user_payload_only_not_system_prompt(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.services.assessment_ai.get_llm_api_key", lambda: "test-key")
    snapshot = ConfirmedModelSnapshot("m1", "p1", "v1.0", (ConfirmedCompetency("c1", "系统设计", "", 1.0, ()),))
    reference = ResumeReference(item_id="r1", item_type="project", prompt_hint="UNTRUSTED_MARKER")
    captured = {}

    def transport(payload, **_kwargs):
        captured.update(payload)
        return {"choices": [{"message": {"content": '{"content":"请举例","covered_competency_ids":["c1"],"turn_type":"MAIN_QUESTION"}'}}]}

    generate_main_question(snapshot, list(snapshot.competencies), [], [], transport, resume_reference=reference)
    assert "UNTRUSTED_MARKER" not in captured["messages"][0]["content"]
    assert "UNTRUSTED_MARKER" in captured["messages"][1]["content"]


def test_main_question_rejects_mismatched_background_display_summary(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.services.assessment_ai.get_llm_api_key", lambda: "test-key")
    snapshot = ConfirmedModelSnapshot("m1", "p1", "v1.0", (ConfirmedCompetency("c1", "系统设计", "", 1.0, ()),))
    reference = ResumeReference(item_id="r1", item_type="project", prompt_hint="供应链平台项目，负责系统设计与交付。")

    def transport(payload, **_kwargs):
        return {"choices": [{"message": {"content": '{"content":"请确认项目中的系统设计贡献","covered_competency_ids":["c1"],"turn_type":"MAIN_QUESTION","background_reference":{"source_type":"BACKGROUND_ONLY","item_id":"r1","item_type":"project","display_summary":"不一致的摘要"}}'}}]}

    with pytest.raises(InvalidAIResponse):
        generate_main_question(snapshot, list(snapshot.competencies), [], [], transport, resume_reference=reference)


def test_analyze_transport_receives_competency_and_evidence(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.services.assessment_ai.get_llm_api_key", lambda: "test-key")
    monkeypatch.setattr("backend.app.services.assessment_ai.is_llm_analysis_enabled", lambda: True)
    snapshot = ConfirmedModelSnapshot("m1", "p1", "v1.0", (ConfirmedCompetency("c1", "系统设计", "", 1.0, ()),))
    captured = {}
    def transport(payload, **_kwargs):
        captured.update(payload)
        return {"choices": [{"message": {"content": '{"answer_summary":"回答","evidence":[{"competency_id":"c1","type":"POSITIVE","excerpt":"回答","summary":"","confidence":0.8}],"evidence_sufficiency":"SUFFICIENT","needs_follow_up":false,"follow_up_reason":"","follow_up_question":""}'}}]}
    analyze_answer(snapshot, snapshot.competencies[0], [{"id": "e1", "excerpt": "证据"}], [], "回答", transport)
    assert "系统设计" in captured["messages"][0]["content"]
    assert "证据" in captured["messages"][1]["content"]


def test_missing_key_and_bad_provider_response_are_retryable(monkeypatch) -> None:
    snapshot = ConfirmedModelSnapshot("m1", "p1", "v1.0", (ConfirmedCompetency("c1", "系统设计", "", 1.0, ()),))
    monkeypatch.setattr("backend.app.services.assessment_ai.get_llm_api_key", lambda: None)
    with pytest.raises(RetryableAIError):
        generate_main_question(snapshot, list(snapshot.competencies), [], [])
    monkeypatch.setattr("backend.app.services.assessment_ai.get_llm_api_key", lambda: "test-key")
    with pytest.raises(RetryableAIError):
        generate_main_question(snapshot, list(snapshot.competencies), [], [], lambda *_args, **_kwargs: {})


def test_missing_key_uses_deterministic_demo_analysis(monkeypatch) -> None:
    snapshot = ConfirmedModelSnapshot("m1", "p1", "v1.0", (ConfirmedCompetency("c1", "系统设计", "", 1.0, ()),))
    monkeypatch.setattr("backend.app.services.assessment_ai.get_llm_api_key", lambda: None)

    result = analyze_answer(snapshot, snapshot.competencies[0], [], [], "我在项目中负责系统设计并完成了容量评估")

    assert result.evidence_sufficiency == "SUFFICIENT"
    assert result.needs_follow_up is False
    assert result.evidence[0].competency_id == "c1"
    assert result.evidence[0].excerpt == "我在项目中负责系统设计并完成了容量评估"


def test_provider_failure_falls_back_to_demo_analysis(monkeypatch) -> None:
    snapshot = ConfirmedModelSnapshot("m1", "p1", "v1.0", (ConfirmedCompetency("c1", "系统设计", "", 1.0, ()),))
    monkeypatch.setattr("backend.app.services.assessment_ai.get_llm_api_key", lambda: "configured-key")
    monkeypatch.setattr("backend.app.services.assessment_ai.is_llm_analysis_enabled", lambda: True)

    def unavailable(*_args, **_kwargs):
        raise RetryableAIError("provider unavailable")

    monkeypatch.setattr("backend.app.services.assessment_ai._call_structured", unavailable)
    with pytest.raises(RetryableAIError, match="provider unavailable"):
        analyze_answer(snapshot, snapshot.competencies[0], [], [], "不知道")
