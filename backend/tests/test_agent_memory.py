from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.agent.memory import AssessmentMemory
from backend.app.db import Base
from backend.app.models import (
    AssessmentSession,
    AssessmentSessionStatus,
    AssessmentTurn,
    AssessmentTurnRole,
    AssessmentTurnType,
    CompetencyAssessment,
    CompetencyAssessmentEvidenceSufficiency,
    CompetencyAssessmentStatus,
    EvidenceObservation,
    EvidenceType,
    ModelSnapshot,
    ModelVersion,
    ModelVersionStatus,
    Project,
)


def test_memory_is_session_scoped_and_preserves_snapshot_order() -> None:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    with Session() as db:
        first_project = Project(id="p-1", name="第一岗位")
        second_project = Project(id="p-2", name="第二岗位")
        db.add_all([first_project, second_project])
        first_model = ModelVersion(
            id="m-1",
            project_id=first_project.id,
            version="v1.0",
            status=ModelVersionStatus.CONFIRMED,
        )
        second_model = ModelVersion(
            id="m-2",
            project_id=second_project.id,
            version="v1.0",
            status=ModelVersionStatus.CONFIRMED,
        )
        db.add_all([first_model, second_model])
        db.flush()
        db.add_all(
            [
                ModelSnapshot(
                    model_version_id=first_model.id,
                    version="v1.0",
                    snapshot_json={
                        "project_id": first_project.id,
                        "competencies": [
                            {"id": "c-1", "name": "系统设计", "description": "", "weight": 0.6, "evidence_ids": []},
                            {"id": "c-2", "name": "问题分析", "description": "", "weight": 0.4, "evidence_ids": []},
                        ],
                    },
                ),
                ModelSnapshot(
                    model_version_id=second_model.id,
                    version="v1.0",
                    snapshot_json={
                        "project_id": second_project.id,
                        "competencies": [
                            {"id": "other", "name": "其他能力", "description": "", "weight": 1.0, "evidence_ids": []}
                        ],
                    },
                ),
            ]
        )
        first_session = AssessmentSession(
            id="s-1",
            project_id=first_project.id,
            model_version_id=first_model.id,
            status=AssessmentSessionStatus.IN_PROGRESS,
            current_competency_id="c-2",
        )
        second_session = AssessmentSession(
            id="s-2",
            project_id=second_project.id,
            model_version_id=second_model.id,
            status=AssessmentSessionStatus.IN_PROGRESS,
            current_competency_id="other",
        )
        db.add_all([first_session, second_session])
        db.flush()
        first_item = CompetencyAssessment(
            id="ca-1",
            session_id=first_session.id,
            competency_id="c-1",
            status=CompetencyAssessmentStatus.SUFFICIENT,
            evidence_sufficiency=CompetencyAssessmentEvidenceSufficiency.SUFFICIENT,
        )
        second_item = CompetencyAssessment(
            id="ca-2",
            session_id=first_session.id,
            competency_id="c-2",
            status=CompetencyAssessmentStatus.ASKING,
        )
        other_item = CompetencyAssessment(
            id="ca-other",
            session_id=second_session.id,
            competency_id="other",
            status=CompetencyAssessmentStatus.ASKING,
        )
        db.add_all([second_item, first_item, other_item])
        db.flush()
        first_question = AssessmentTurn(
            id="t-q1",
            session_id=first_session.id,
            competency_assessment_id=first_item.id,
            turn_index=1,
            role=AssessmentTurnRole.SYSTEM,
            turn_type=AssessmentTurnType.MAIN_QUESTION,
            content="问题一",
            covered_competency_ids=["c-1"],
        )
        first_answer = AssessmentTurn(
            id="t-a1",
            session_id=first_session.id,
            competency_assessment_id=first_item.id,
            turn_index=2,
            role=AssessmentTurnRole.USER,
            turn_type=AssessmentTurnType.ANSWER,
            content="回答一",
            covered_competency_ids=["c-1"],
        )
        other_turn = AssessmentTurn(
            id="t-other",
            session_id=second_session.id,
            competency_assessment_id=other_item.id,
            turn_index=1,
            role=AssessmentTurnRole.USER,
            turn_type=AssessmentTurnType.ANSWER,
            content="其他回答",
            covered_competency_ids=["other"],
        )
        db.add_all([first_answer, other_turn, first_question])
        db.flush()
        db.add_all(
            [
                EvidenceObservation(
                    id="e-1",
                    session_id=first_session.id,
                    competency_assessment_id=first_item.id,
                    competency_id="c-1",
                    turn_id=first_answer.id,
                    evidence_type=EvidenceType.POSITIVE,
                    excerpt="回答一",
                    source_excerpt="回答一",
                    summary="有系统设计实践",
                    confidence=0.8,
                ),
                EvidenceObservation(
                    id="e-other",
                    session_id=second_session.id,
                    competency_assessment_id=other_item.id,
                    competency_id="other",
                    turn_id=other_turn.id,
                    evidence_type=EvidenceType.POSITIVE,
                    excerpt="其他回答",
                    source_excerpt="其他回答",
                    summary="其他证据",
                    confidence=0.9,
                ),
            ]
        )
        db.flush()

        memory = AssessmentMemory(db)
        conversation = memory.get_conversation(first_session.id)
        evidence = memory.get_evidence(first_session.id)
        context = memory.get_context(first_session)

        assert [item.content for item in conversation] == ["问题一", "回答一"]
        assert [item.source_excerpt for item in evidence] == ["回答一"]
        assert all(item.turn_id != other_turn.id for item in conversation)
        assert [item.competency_id for item in context.competencies] == ["c-1", "c-2"]
        assert context.session_id == first_session.id
        assert context.remaining_competency_ids == ["c-2"]
        assert not db.dirty
