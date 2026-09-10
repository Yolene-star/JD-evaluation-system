import subprocess
import sys

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.agent.interview_agent import InterviewAgent
from backend.app.agent.schemas import AgentAction, AgentPhase
from backend.app.db import Base
from backend.app.models import (
    AssessmentEvent,
    AssessmentSession,
    AssessmentSessionStatus,
    AssessmentTurn,
    AssessmentTurnRole,
    AssessmentTurnType,
    CompetencyAssessment,
    CompetencyAssessmentStatus,
    Evidence,
    EvidenceObservation,
    JobDescription,
    ModelSnapshot,
    ModelVersion,
    ModelVersionStatus,
    Project,
)
from backend.app.services.assessment_ai import (
    AnalysisResult,
    EvidenceResult,
    GeneratedQuestion,
    RetryableAIError,
)
from backend.app.services.assessment_state import start_session
from backend.app.services.assessment_contracts import get_confirmed_model_snapshot


class FixedEvidenceTool:
    def __init__(self, sufficiency: str) -> None:
        self.sufficiency = sufficiency

    def analyze(self, *, competency, answer, **_kwargs):
        sufficient = self.sufficiency == "SUFFICIENT"
        return AnalysisResult(
            answer_summary=answer,
            evidence=[
                EvidenceResult(
                    competency_id=competency.id,
                    type="POSITIVE" if sufficient else "UNCERTAIN",
                    excerpt=answer,
                    summary="回答证据",
                    confidence=0.8 if sufficient else 0.4,
                )
            ],
            evidence_sufficiency=self.sufficiency,
            needs_follow_up=not sufficient,
            follow_up_reason="缺少结果证据" if not sufficient else "",
            follow_up_question="请补充项目结果" if not sufficient else "",
        )


class FailingEvidenceTool:
    def analyze(self, **_kwargs):
        raise RetryableAIError("temporary provider failure")


class FixedQuestionTool:
    def generate(self, *, competencies, **_kwargs):
        return GeneratedQuestion(
            content=f"请介绍{competencies[0].name}经历",
            covered_competency_ids=[competencies[0].id],
            turn_type="MAIN_QUESTION",
        )

    def generate_follow_up(self, *, competency, analysis, **_kwargs):
        return GeneratedQuestion(
            content=analysis.follow_up_question,
            covered_competency_ids=[competency.id],
            turn_type="FOLLOW_UP",
            evaluation_target=analysis.follow_up_reason,
        )


def session_factory(competency_count: int = 2):
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    db = Session()
    project = Project(id="p-1", name="Agent 测试")
    model = ModelVersion(
        id="m-1",
        project_id=project.id,
        version="v1.0",
        status=ModelVersionStatus.CONFIRMED,
    )
    db.add_all([project, model])
    db.flush()
    competencies = [
        {"id": f"c-{index}", "name": f"能力{index}", "description": "", "weight": 1 / competency_count, "evidence_ids": []}
        for index in range(1, competency_count + 1)
    ]
    db.add(
        ModelSnapshot(
            model_version_id=model.id,
            version="v1.0",
            snapshot_json={"project_id": project.id, "competencies": competencies},
        )
    )
    db.flush()
    session = AssessmentSession(
        id="s-1",
        project_id=project.id,
        model_version_id=model.id,
    )
    db.add(session)
    db.flush()
    snapshot = get_confirmed_model_snapshot(db, project.id, model.id)
    start_session(db, session, snapshot)
    first = db.scalar(
        select(CompetencyAssessment).where(
            CompetencyAssessment.session_id == session.id,
            CompetencyAssessment.competency_id == "c-1",
        )
    )
    question = AssessmentTurn(
        session_id=session.id,
        competency_assessment_id=first.id,
        turn_index=1,
        role=AssessmentTurnRole.SYSTEM,
        turn_type=AssessmentTurnType.MAIN_QUESTION,
        content="初始问题",
        covered_competency_ids=["c-1"],
    )
    answer = AssessmentTurn(
        session_id=session.id,
        competency_assessment_id=first.id,
        turn_index=2,
        role=AssessmentTurnRole.USER,
        turn_type=AssessmentTurnType.ANSWER,
        content="我负责了方案设计并交付",
        covered_competency_ids=["c-1"],
        idempotency_key="answer-1",
    )
    db.add_all([question, answer])
    db.flush()
    return db, session, answer


def test_interview_agent_records_evidence_and_creates_targeted_follow_up() -> None:
    db, session, answer = session_factory()
    try:
        result = InterviewAgent(
            db,
            evidence_tool=FixedEvidenceTool("INSUFFICIENT"),
            question_tool=FixedQuestionTool(),
        ).process_turn(session, answer)

        item = db.scalar(
            select(CompetencyAssessment).where(
                CompetencyAssessment.session_id == session.id,
                CompetencyAssessment.competency_id == "c-1",
            )
        )
        observations = list(
            db.scalars(select(EvidenceObservation).where(EvidenceObservation.turn_id == answer.id))
        )
        assert result.decision.action is AgentAction.FOLLOW_UP
        assert result.agent_status.phase is AgentPhase.FOLLOWING_UP
        assert result.current_question["turn_type"] == "FOLLOW_UP"
        assert result.current_question["content"] == "请补充项目结果"
        assert item.status is CompetencyAssessmentStatus.FOLLOW_UP
        assert len(observations) == 1
        assert observations[0].source_excerpt == answer.content
    finally:
        db.close()


def test_interview_agent_advances_or_finishes_only_via_state_machine() -> None:
    db, session, answer = session_factory(competency_count=1)
    try:
        result = InterviewAgent(
            db,
            evidence_tool=FixedEvidenceTool("SUFFICIENT"),
            question_tool=FixedQuestionTool(),
        ).process_turn(session, answer)

        assert result.decision.action is AgentAction.FINISH
        assert result.agent_status.phase is AgentPhase.COMPLETED
        assert session.status is AssessmentSessionStatus.COMPLETED
        assert result.current_question is None
        actions = [
            event.action
            for event in db.scalars(
                select(AssessmentEvent).where(AssessmentEvent.session_id == session.id)
            )
        ]
        assert "ANSWER_ANALYZED" in actions
        assert "ASSESSMENT_COMPLETED" in actions
    finally:
        db.close()


def test_interview_agent_retryable_failure_preserves_answer_and_state() -> None:
    db, session, answer = session_factory()
    try:
        result = InterviewAgent(
            db,
            evidence_tool=FailingEvidenceTool(),
            question_tool=FixedQuestionTool(),
        ).process_turn(session, answer)

        item = db.scalar(
            select(CompetencyAssessment).where(
                CompetencyAssessment.session_id == session.id,
                CompetencyAssessment.competency_id == "c-1",
            )
        )
        assert result.retryable is True
        assert result.agent_status.phase is AgentPhase.RETRY_REQUIRED
        assert item.status is CompetencyAssessmentStatus.ASKING
        assert db.get(AssessmentTurn, answer.id).content == answer.content
        assert list(
            db.scalars(select(EvidenceObservation).where(EvidenceObservation.turn_id == answer.id))
        ) == []
    finally:
        db.close()


def test_interview_agent_passes_frozen_answer_competency_jd_evidence_and_prior_transcript() -> None:
    db, session, answer = session_factory()
    captured: dict = {}
    try:
        jd = JobDescription(project_id=session.project_id, title="后端工程师", raw_text="负责系统设计；完成容量评估。")
        db.add(jd)
        db.flush()
        referenced = Evidence(jd_id=jd.id, excerpt="负责系统设计")
        unrelated = Evidence(jd_id=jd.id, excerpt="完成容量评估")
        db.add_all([referenced, unrelated])
        db.flush()
        snapshot = db.scalar(select(ModelSnapshot).where(ModelSnapshot.model_version_id == session.model_version_id))
        snapshot.snapshot_json = {
            "project_id": session.project_id,
            "competencies": [
                {
                    "id": "c-1",
                    "name": "系统设计",
                    "description": "设计可靠系统",
                    "weight": 1.0,
                    "jd_evidence_ids": [referenced.id],
                    "indicators": ["容量与可靠性权衡"],
                    "evidence_requirements": ["本人行动", "可验证结果"],
                },
                {"id": "c-2", "name": "能力2", "description": "", "weight": 0.0, "jd_evidence_ids": []},
            ],
        }
        db.flush()

        class CapturingEvidenceTool(FixedEvidenceTool):
            def analyze(self, **kwargs):
                captured.update(kwargs)
                return super().analyze(**kwargs)

        InterviewAgent(
            db,
            evidence_tool=CapturingEvidenceTool("SUFFICIENT"),
            question_tool=FixedQuestionTool(),
        ).process_turn(session, answer)

        assert captured["answer"] == answer.content
        assert captured["competency"].id == "c-1"
        assert captured["competency"].indicators == ("容量与可靠性权衡",)
        assert captured["competency"].evidence_requirements == ("本人行动", "可验证结果")
        assert captured["jd_evidence"] == [{"id": referenced.id, "excerpt": "负责系统设计"}]
        assert all(item["content"] != answer.content for item in captured["transcript"])
        assert any(item["content"] == "初始问题" for item in captured["transcript"])
    finally:
        db.close()


def test_interview_agent_import_does_not_load_stage_three_tools() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import backend.app.agent.interview_agent; "
                "blocked = {'backend.app.services.scoring', 'backend.app.services.report_service'}; "
                "loaded = sorted(blocked.intersection(sys.modules)); "
                "sys.stderr.write(','.join(loaded)); "
                "sys.exit(1 if loaded else 0)"
            ),
        ],
        cwd=".",
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
