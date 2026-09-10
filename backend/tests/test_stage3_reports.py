import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db import Base
from backend.app.models import (
    AssessmentCompletion,
    AssessmentSession,
    AssessmentSessionStatus,
    ModelVersion,
    Project,
    ReportNarrativeStatus,
    RubricSetStatus,
)
from backend.app.services.report_service import generate_report
from backend.app.services.rubrics import activate_rubric_set, create_default_rubric_set


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def setup_function() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def _fixture(db):
    project = Project(name="reports")
    db.add(project)
    db.flush()
    model = ModelVersion(project_id=project.id, version="v1", status="CONFIRMED")
    db.add(model)
    db.flush()
    session = AssessmentSession(project_id=project.id, model_version_id=model.id, status=AssessmentSessionStatus.COMPLETED, completion=AssessmentCompletion.FULL)
    db.add(session)
    db.flush()
    rubric = create_default_rubric_set(db, model.id, [{"id": "c1", "name": "系统设计", "weight": 1.0, "indicators": ["i1"]}])
    activate_rubric_set(db, rubric.id)
    db.commit()
    package = {"session_id": session.id, "model_version_id": model.id, "completion": "FULL", "competencies": [{"competency_id": "c1", "status": "SUFFICIENT", "observations": [{"id": "e1", "type": "POSITIVE", "excerpt": "evidence", "confidence": 0.9}]}]}
    return session, rubric, package


def test_same_idempotency_key_returns_existing_report() -> None:
    with SessionLocal() as db:
        session, rubric, package = _fixture(db)
        first = generate_report(db, session.id, "ep-1", package, rubric.id, "key-1", narrative_adapter=lambda _: {"overview": "ok"})
        second = generate_report(db, session.id, "ep-1", package, rubric.id, "key-1", narrative_adapter=lambda _: {"overview": "different"})
        assert second.id == first.id
        assert second.report_version == 1


def test_recalculation_creates_new_report_version() -> None:
    with SessionLocal() as db:
        session, rubric, package = _fixture(db)
        first = generate_report(db, session.id, "ep-1", package, rubric.id, "key-1")
        second = generate_report(db, session.id, "ep-1", package, rubric.id, "key-2")
        assert second.id != first.id
        assert second.report_version == 2


def test_narrative_failure_keeps_ready_base_report() -> None:
    with SessionLocal() as db:
        session, rubric, package = _fixture(db)

        def broken(_: dict):
            raise RuntimeError("provider unavailable")

        report = generate_report(db, session.id, "ep-1", package, rubric.id, "key-1", narrative_adapter=broken)
        assert report.status.value == "READY"
        assert report.evaluations[0].score is not None
        assert report.narrative_status is ReportNarrativeStatus.PENDING_RETRY

def test_invalid_evidence_reference_downgrades_narrative_to_retry() -> None:
    with SessionLocal() as db:
        session, rubric, package = _fixture(db)
        report = generate_report(db, session.id, "ep-1", package, rubric.id, "key-1", narrative_adapter=lambda _: {"overview": "ok", "evidence_ids": ["missing"]})
        assert report.status.value == "READY"
        assert report.narrative_status is ReportNarrativeStatus.PENDING_RETRY
