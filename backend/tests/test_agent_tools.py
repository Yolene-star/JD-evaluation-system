from types import SimpleNamespace

from backend.app.agent.tools import EvidenceTool, QuestionTool, ReportTool, ScoringTool
from backend.app.services.assessment_ai import GeneratedQuestion


def test_question_tool_forwards_agent_context_and_preserves_metadata() -> None:
    captured: dict = {}

    def generate(
        snapshot,
        competencies,
        jd_evidence,
        transcript,
        transport=None,
        *,
        agent_context=None,
    ):
        captured["agent_context"] = agent_context
        return GeneratedQuestion(
            content="请说明量化结果",
            covered_competency_ids=["c-1"],
            turn_type="MAIN_QUESTION",
            evaluation_target="验证结果",
            expected_evidence=["指标变化"],
        )

    result = QuestionTool(generate_fn=generate).generate(
        snapshot=object(),
        competencies=[object()],
        jd_evidence=[],
        transcript=[],
        agent_context={"missing_information": ["结果"]},
    )

    assert result.evaluation_target == "验证结果"
    assert result.expected_evidence == ["指标变化"]
    assert captured["agent_context"]["missing_information"] == ["结果"]


def test_question_tool_builds_follow_up_from_validated_analysis() -> None:
    result = QuestionTool().generate_follow_up(
        competency=SimpleNamespace(id="c-1"),
        analysis=SimpleNamespace(
            follow_up_question="请补充项目结果",
            follow_up_reason="缺少结果证据",
        ),
    )

    assert result.turn_type == "FOLLOW_UP"
    assert result.covered_competency_ids == ["c-1"]
    assert result.content == "请补充项目结果"
    assert result.evaluation_target == "缺少结果证据"


def test_evidence_tool_returns_validated_analysis_unchanged() -> None:
    expected = SimpleNamespace(evidence_sufficiency="SUFFICIENT")

    def analyze(snapshot, competency, jd_evidence, transcript, answer, transport=None):
        assert answer == "回答原文"
        return expected

    result = EvidenceTool(analyze_fn=analyze).analyze(
        snapshot=object(),
        competency=object(),
        jd_evidence=[],
        transcript=[],
        answer="回答原文",
    )

    assert result is expected


def test_scoring_tool_delegates_to_stage_three_scoring_service() -> None:
    expected = SimpleNamespace(match_score=82.0)

    def score(package, rubrics):
        assert package == {"completion": "FULL"}
        assert rubrics == {"c-1": {"weight": 1.0}}
        return expected

    result = ScoringTool(score_fn=score).score(
        {"completion": "FULL"},
        {"c-1": {"weight": 1.0}},
    )

    assert result is expected


def test_report_tool_forwards_existing_report_contract() -> None:
    expected = SimpleNamespace(id="report-1")
    captured: dict = {}

    def generate(db, session_id, evidence_package_id, evidence_package, rubric_set_id, idempotency_key, *, narrative_adapter=None):
        captured.update(
            session_id=session_id,
            evidence_package_id=evidence_package_id,
            rubric_set_id=rubric_set_id,
            idempotency_key=idempotency_key,
            narrative_adapter=narrative_adapter,
        )
        return expected

    adapter = object()
    result = ReportTool(generate_fn=generate).generate(
        db=object(),
        session_id="session-1",
        evidence_package_id="package-1",
        evidence_package={"completion": "FULL"},
        rubric_set_id="rubric-1",
        idempotency_key="request-1",
        narrative_adapter=adapter,
    )

    assert result is expected
    assert captured == {
        "session_id": "session-1",
        "evidence_package_id": "package-1",
        "rubric_set_id": "rubric-1",
        "idempotency_key": "request-1",
        "narrative_adapter": adapter,
    }
