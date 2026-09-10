import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db import Base
from backend.app.models import (
    AssessmentReport,
    CompetencyEvaluation,
    CompetencyRubric,
    ModelVersion,
    Project,
    ReportNarrative,
    RubricSet,
    RubricSetStatus,
    AssessmentReportStatus,
)
from backend.app.services.rubrics import activate_rubric_set, create_default_rubric_set


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def setup_function() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def _model(db):
    project = Project(name="stage3")
    db.add(project)
    db.flush()
    model = ModelVersion(project_id=project.id, version="v1", status="CONFIRMED")
    db.add(model)
    db.flush()
    return model


def test_default_rubric_covers_snapshot_competencies_and_can_activate() -> None:
    with SessionLocal() as db:
        model = _model(db)
        rubric = create_default_rubric_set(db, model.id, [{"id": "c1", "name": "系统设计", "description": "设计", "weight": 0.6}, {"id": "c2", "name": "沟通", "description": "沟通", "weight": 0.4}])
        assert rubric.status is RubricSetStatus.DRAFT
        assert {item.competency_id for item in rubric.competencies} == {"c1", "c2"}
        activate_rubric_set(db, rubric.id)
        db.commit()
        assert rubric.status is RubricSetStatus.ACTIVE


def test_active_rubric_is_immutable() -> None:
    with SessionLocal() as db:
        model = _model(db)
        rubric = create_default_rubric_set(db, model.id, [{"id": "c1", "name": "系统设计", "description": "设计", "weight": 1.0}])
        activate_rubric_set(db, rubric.id)
        db.commit()
        rubric.version = "changed"
        with pytest.raises((ValueError, RuntimeError)):
            db.commit()


def test_active_rubric_children_are_immutable_and_old_active_can_retire() -> None:
    with SessionLocal() as db:
        model = _model(db)
        first = create_default_rubric_set(db, model.id, [{"id": "c1", "name": "系统设计", "weight": 1.0}])
        activate_rubric_set(db, first.id)
        db.commit()
        first.competencies[0].indicators = ["改写"]
        with pytest.raises((ValueError, RuntimeError)):
            db.commit()
        db.rollback()
        second = create_default_rubric_set(db, model.id, [{"id": "c1", "name": "系统设计", "weight": 1.0}], version="r2")
        activate_rubric_set(db, second.id)
        db.commit()
        assert first.status is RubricSetStatus.RETIRED


def test_report_models_keep_versioned_references_and_narrative() -> None:
    with SessionLocal() as db:
        model = _model(db)
        rubric = RubricSet(model_version_id=model.id, version="r1", status=RubricSetStatus.DRAFT, scoring_rule_version="stage3-v1")
        db.add(rubric)
        db.flush()
        report = AssessmentReport(assessment_session_id="s1", report_version=1, evidence_package_id="ep1", model_version_id=model.id, rubric_set_id=rubric.id, scoring_rule_version="stage3-v1", completion="FULL", status=AssessmentReportStatus.READY)
        db.add(report)
        db.flush()
        evaluation = CompetencyEvaluation(report_id=report.id, competency_id="c1", status="INCOMPLETE", score=None, attainment=None, evidence_ids=[])
        db.add(evaluation)
        db.add(ReportNarrative(report_id=report.id, overview="概览", strengths=[], weaknesses=[], recommendations=[], cited_evidence_ids=[]))
        db.commit()
        assert report.report_version == 1
        assert evaluation.score is None and evaluation.attainment is None
