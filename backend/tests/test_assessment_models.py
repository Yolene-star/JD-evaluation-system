from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db import Base, engine
from backend.app.models import (
    AssessmentCompletion,
    AssessmentSessionStatus,
    AssessmentTurn,
    AssessmentTurnRole,
    AssessmentTurnType,
    CompetencyAssessment,
    CompetencyAssessmentEvidenceSufficiency,
    EvidenceObservation,
    EvidenceType,
    JobDescription,
    JobDescriptionStatus,
    Competency,
    ModelSnapshot,
    ModelVersion,
    ModelVersionStatus,
    Project,
)
from backend.app.schemas import (
    AssessmentSessionResponse,
    AssessmentTurnResponse,
    CompetencyAssessmentResponse,
    EvidenceObservationResponse,
)
from backend.app.services.assessment_contracts import (
    ModelNotConfirmedError,
    create_assessment_session,
    get_confirmed_model_snapshot,
)


test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(bind=test_engine, expire_on_commit=False)


def _enable_test_foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


event.listen(test_engine, "connect", _enable_test_foreign_keys)


@pytest.fixture(autouse=True)
def create_tables() -> None:
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)


def _confirmed_snapshot() -> tuple[str, str]:
    project = Project(name="阶段二模型契约")
    with TestSessionLocal() as db:
        db.add(project)
        db.flush()
        model = ModelVersion(project_id=project.id, version="v1.0", status=ModelVersionStatus.CONFIRMED)
        db.add(model)
        db.flush()
        db.add(
            ModelSnapshot(
                model_version_id=model.id,
                version="v1.0",
                snapshot_json={
                    "project_id": project.id,
                    "competencies": [
                        {"id": "c-2", "name": "问题分析", "description": "拆解问题", "weight": 0.7, "evidence_ids": ["e-2"]},
                        {"id": "c-1", "name": "系统设计", "description": "设计方案", "weight": 0.3, "evidence_ids": ["e-1"]},
                    ],
                },
            )
        )
        db.commit()
        return project.id, model.id


def test_draft_snapshot_is_rejected() -> None:
    with TestSessionLocal() as db:
        project = Project(name="草稿拒绝")
        db.add(project)
        db.flush()
        model = ModelVersion(project_id=project.id, status=ModelVersionStatus.DRAFT)
        db.add(model)
        db.commit()
        with pytest.raises(ModelNotConfirmedError):
            get_confirmed_model_snapshot(db, project.id, model.id)


def test_confirmed_snapshot_preserves_stored_order_and_immutable_fields() -> None:
    project_id, model_id = _confirmed_snapshot()
    with TestSessionLocal() as db:
        snapshot = get_confirmed_model_snapshot(db, project_id, model_id)
    assert [item.id for item in snapshot.competencies] == ["c-2", "c-1"]
    assert [item.weight for item in snapshot.competencies] == [0.7, 0.3]
    assert [item.jd_evidence_ids for item in snapshot.competencies] == [("e-2",), ("e-1",)]
    assert snapshot.project_id == project_id
    assert snapshot.version == "v1.0"


def test_assessment_session_defaults_to_ready_and_current_competency_is_empty() -> None:
    project_id, model_id = _confirmed_snapshot()
    with TestSessionLocal() as db:
        created = create_assessment_session(db, project_id, model_id)
        assert created.status == AssessmentSessionStatus.READY
        assert created.current_competency_id is None
        assert created.id
        assert created.created_at is not None


def test_assessment_tables_have_required_indexes_and_foreign_keys() -> None:
    inspector = inspect(test_engine)
    for table in ("assessment_sessions", "competency_assessments", "assessment_turns", "evidence_observations", "assessment_events"):
        assert inspector.has_table(table)
    indexes = {index["name"] for index in inspector.get_indexes("assessment_turns")}
    assert any("idempotency" in (name or "") for name in indexes)
    assert any("session" in (name or "") for name in indexes)
    assert any("current_competency" in (index["name"] or "") for index in inspector.get_indexes("assessment_sessions"))
    assert inspector.get_foreign_keys("assessment_turns")
    assert inspector.get_foreign_keys("evidence_observations")
    assert "created_at" in {column["name"] for column in inspector.get_columns("competency_assessments")}
    assert "created_at" in {column["name"] for column in inspector.get_columns("evidence_observations")}


def test_turn_idempotency_is_unique_per_session_when_key_present() -> None:
    project_id, model_id = _confirmed_snapshot()
    with TestSessionLocal() as db:
        session = create_assessment_session(db, project_id, model_id)
        db.add_all(
            [
                AssessmentTurn(session_id=session.id, role=AssessmentTurnRole.USER, turn_type=AssessmentTurnType.ANSWER, content="a", idempotency_key="same"),
                AssessmentTurn(session_id=session.id, role=AssessmentTurnRole.USER, turn_type=AssessmentTurnType.ANSWER, content="b", idempotency_key="same"),
            ]
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_assessment_schemas_validate_orm_shaped_payloads() -> None:
    now = datetime.now(timezone.utc)
    session = AssessmentSessionResponse(id="s1", project_id="p1", model_version_id="m1", status=AssessmentSessionStatus.READY, current_competency_id=None, created_at=now, updated_at=now)
    competency = CompetencyAssessmentResponse(id="ca1", session_id="s1", competency_id="c1", status="PENDING", follow_up_count=0, created_at=now)
    turn = AssessmentTurnResponse(id="t1", session_id="s1", role=AssessmentTurnRole.SYSTEM, turn_type=AssessmentTurnType.MAIN_QUESTION, content="问题", covered_competency_ids=["c1"], idempotency_key=None, created_at=now)
    evidence = EvidenceObservationResponse(id="e1", session_id="s1", competency_assessment_id="ca1", competency_id="c1", turn_id="t1", evidence_type=EvidenceType.POSITIVE, excerpt="原文", confidence=0.8, created_at=now)
    assert session.status is AssessmentSessionStatus.READY
    assert competency.follow_up_count == 0
    assert turn.covered_competency_ids == ["c1"]
    assert evidence.confidence == 0.8


def test_evidence_observation_requires_competency_assessment_foreign_key() -> None:
    project_id, model_id = _confirmed_snapshot()
    with TestSessionLocal() as db:
        session = create_assessment_session(db, project_id, model_id)
        db.add(EvidenceObservation(session_id=session.id, competency_id="c-1", turn_id="t1", evidence_type=EvidenceType.POSITIVE, excerpt="原文"))
        with pytest.raises(IntegrityError):
            db.commit()


def test_evidence_observation_rejects_unknown_competency_assessment() -> None:
    project_id, model_id = _confirmed_snapshot()
    with TestSessionLocal() as db:
        jd = JobDescription(
            project_id=project_id,
            title="约束测试",
            raw_text="测试",
            status=JobDescriptionStatus.COMPLETED,
        )
        db.add(jd)
        db.flush()
        db.add(Competency(id="c-1", jd_id=jd.id, name="系统设计"))
        session = create_assessment_session(db, project_id, model_id)
        turn = AssessmentTurn(
            session_id=session.id,
            role=AssessmentTurnRole.USER,
            turn_type=AssessmentTurnType.ANSWER,
            content="回答",
        )
        db.add(turn)
        db.flush()
        db.add(
            EvidenceObservation(
                session_id=session.id,
                competency_id="c-1",
                competency_assessment_id="missing-owner",
                turn_id=turn.id,
                evidence_type=EvidenceType.UNCERTAIN,
                excerpt="回答",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_default_sqlite_engine_enforces_foreign_keys() -> None:
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1


def test_state_fields_and_completion_schema_are_persisted() -> None:
    project_id, model_id = _confirmed_snapshot()
    with TestSessionLocal() as db:
        session = create_assessment_session(db, project_id, model_id)
        session.completion = AssessmentCompletion.NONE
        session.started_at = now = datetime.now(timezone.utc)
        session.paused_at = now
        session.completed_at = now
        assessment = CompetencyAssessment(
            session_id=session.id,
            competency_id="c-1",
            main_question="请举例",
            evidence_sufficiency=CompetencyAssessmentEvidenceSufficiency.UNCERTAIN,
            started_at=now,
            completed_at=now,
        )
        db.add(assessment)
        db.flush()
        turn = AssessmentTurn(session_id=session.id, competency_assessment_id=assessment.id, turn_index=1, role=AssessmentTurnRole.SYSTEM, turn_type=AssessmentTurnType.MAIN_QUESTION, content="问题")
        db.add(turn)
        db.commit()
        assert session.completion is AssessmentCompletion.NONE
        assert assessment.main_question == "请举例"
        assert turn.turn_index == 1


def test_current_competency_accepts_snapshot_local_id() -> None:
    project_id, model_id = _confirmed_snapshot()
    with TestSessionLocal() as db:
        session = create_assessment_session(db, project_id, model_id)
        session.current_competency_id = "c-2"
        db.commit()
        assert session.current_competency_id == "c-2"


def test_explicit_empty_model_version_is_rejected() -> None:
    project_id, _ = _confirmed_snapshot()
    with TestSessionLocal() as db, pytest.raises(ModelNotConfirmedError):
        get_confirmed_model_snapshot(db, project_id, "")


def test_malformed_snapshot_raises_typed_error() -> None:
    with TestSessionLocal() as db:
        project = Project(name="损坏快照")
        db.add(project)
        db.flush()
        model = ModelVersion(project_id=project.id, version="v1.0", status=ModelVersionStatus.CONFIRMED)
        db.add(model)
        db.flush()
        db.add(ModelSnapshot(model_version_id=model.id, version="v1.0", snapshot_json={"competencies": {"bad": True}}))
        db.commit()
        with pytest.raises(ModelNotConfirmedError):
            get_confirmed_model_snapshot(db, project.id, model.id)


@pytest.mark.parametrize(
    "snapshot_json",
    [
        ["not", "an", "object"],
        {"competencies": [{"id": "c1", "name": "分析", "weight": 1, "evidence_ids": None}]},
    ],
)
def test_other_malformed_snapshots_raise_typed_error(snapshot_json: object) -> None:
    with TestSessionLocal() as db:
        project = Project(name="其他损坏快照")
        db.add(project)
        db.flush()
        model = ModelVersion(project_id=project.id, version="v1.0", status=ModelVersionStatus.CONFIRMED)
        db.add(model)
        db.flush()
        db.add(ModelSnapshot(model_version_id=model.id, version="v1.0", snapshot_json=snapshot_json))
        db.commit()
        with pytest.raises(ModelNotConfirmedError):
            get_confirmed_model_snapshot(db, project.id, model.id)
