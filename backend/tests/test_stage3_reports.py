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
    ModelSnapshot,
    Project,
    ReportNarrativeStatus,
    RubricSetStatus,
)
from backend.app.services.report_service import generate_report
from backend.app.services.rubrics import activate_rubric_set, create_default_rubric_set
from backend.app.services.evidence_package import build_evidence_package
from backend.app.models import CompetencyAssessment, CompetencyAssessmentStatus


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
    db.add(ModelSnapshot(model_version_id=model.id, version="v1", snapshot_json={"competencies": [{"id": "c1", "name": "系统设计", "weight": 1.0}]}))
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

def test_report_includes_deterministic_profile_when_no_llm_adapter_is_available() -> None:
    with SessionLocal() as db:
        session, rubric, package = _fixture(db)
        report = generate_report(db, session.id, "ep-profile", package, rubric.id, "profile-key")
        assert report.narrative is not None
        assert report.narrative.overview
        assert report.narrative_status is ReportNarrativeStatus.READY
        narrative_text = " ".join(item["text"] for item in report.narrative.weaknesses + report.narrative.strengths)
        assert "系统设计" in narrative_text
        assert "c1" not in narrative_text


def test_evidence_package_merges_duplicate_competency_assessments() -> None:
    with SessionLocal() as db:
        session, _rubric, _package = _fixture(db)
        db.add_all([
            CompetencyAssessment(session_id=session.id, competency_id="c1", status=CompetencyAssessmentStatus.INCOMPLETE),
            CompetencyAssessment(session_id=session.id, competency_id="c1", status=CompetencyAssessmentStatus.SUFFICIENT),
        ])
        db.commit()

        package = build_evidence_package(db, session.id)

        assert [item["competency_id"] for item in package["competencies"]] == ["c1"]
