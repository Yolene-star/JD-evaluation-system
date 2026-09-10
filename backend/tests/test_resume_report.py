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
    ResumeContextStatus,
    ResumeContextVersion,
    ResumeSnapshot,
)
from backend.app.routes.reports import _report_payload
from backend.app.services.report_service import generate_report
from backend.app.services.rubrics import activate_rubric_set, create_default_rubric_set


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def setup_function() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def _fixture(db, *, with_resume: bool, project=None, model=None, rubric=None):
    if project is None:
        project = Project(name="report resume")
        db.add(project)
        db.flush()
    if model is None:
        model = ModelVersion(project_id=project.id, version="v1", status="CONFIRMED")
        db.add(model)
        db.flush()
    session = AssessmentSession(
        project_id=project.id,
        model_version_id=model.id,
        status=AssessmentSessionStatus.COMPLETED,
        completion=AssessmentCompletion.FULL,
    )
    db.add(session)
    db.flush()
    if with_resume:
        version = ResumeContextVersion(
            project_id=project.id,
            version=1,
            is_current=True,
            source_filename="resume.txt",
            media_type="text/plain",
            file_size=10,
            content_sha256="a" * 64,
            normalized_text="private resume text",
            structured_context_json={
                "education": [{"id": "edu-1", "summary": "某大学"}],
                "projects": [{"id": "project-1", "summary": "图像项目"}],
                "skills": [{"id": "skill-1", "summary": "Python"}],
                "experiences": [],
            },
            parser_version="resume-v1",
            status=ResumeContextStatus.READY,
        )
        db.add(version)
        db.flush()
        db.add(
            ResumeSnapshot(
                session_id=session.id,
                resume_context_version_id=version.id,
                snapshot_json={
                    "source_type": "BACKGROUND_ONLY",
                    "background": version.structured_context_json,
                    "content_sha256": version.content_sha256,
                    "parser_version": version.parser_version,
                },
            )
        )
    if rubric is None:
        rubric = create_default_rubric_set(db, model.id, [{"id": "c1", "name": "系统设计", "weight": 1.0, "indicators": ["i1"]}])
        activate_rubric_set(db, rubric.id)
    db.commit()
    package = {
        "session_id": session.id,
        "model_version_id": model.id,
        "completion": "FULL",
        "competencies": [
            {
                "competency_id": "c1",
                "status": "SUFFICIENT",
                "observations": [{"id": "e1", "type": "POSITIVE", "excerpt": "面试回答", "confidence": 0.9}],
            }
        ],
    }
    return session, rubric, package


def test_report_keeps_resume_background_separate_from_formal_evidence() -> None:
    with SessionLocal() as db:
        project = Project(name="report resume")
        db.add(project)
        db.flush()
        model = ModelVersion(project_id=project.id, version="v1", status="CONFIRMED")
        db.add(model)
        db.flush()
        rubric = create_default_rubric_set(db, model.id, [{"id": "c1", "name": "系统设计", "weight": 1.0, "indicators": ["i1"]}])
        activate_rubric_set(db, rubric.id)
        with_resume, _, package = _fixture(db, with_resume=True, project=project, model=model, rubric=rubric)
        without_resume, _, _ = _fixture(db, with_resume=False, project=project, model=model, rubric=rubric)
        first = generate_report(db, with_resume.id, "ep-1", package, rubric.id, "key-resume")
        package_without = {**package, "session_id": without_resume.id}
        second = generate_report(db, without_resume.id, "ep-2", package_without, rubric.id, "key-no-resume")

        first_payload = _report_payload(db, first)
        second_payload = _report_payload(db, second)

        assert first_payload["match_score"] == second_payload["match_score"]
        assert first_payload["evaluations"] == second_payload["evaluations"]
        assert first_payload["candidate_background"]["source_type"] == "BACKGROUND_ONLY"
        assert first_payload["candidate_background"]["notice"] == "简历背景信息未作为评分证据"
        assert first_payload["candidate_background"]["projects"][0]["id"] == "project-1"
        assert second_payload["candidate_background"] is None
        assert "private resume text" not in str(first_payload)
        assert "project-1" not in first_payload["evaluations"][0]["evidence_ids"]


def test_report_background_reads_frozen_snapshot_not_current_resume() -> None:
    with SessionLocal() as db:
        session, rubric, package = _fixture(db, with_resume=True)
        report = generate_report(db, session.id, "ep-1", package, rubric.id, "key-stable")
        original = db.query(ResumeContextVersion).filter_by(project_id=session.project_id, is_current=True).one()
        original.is_current = False
        db.add(
            ResumeContextVersion(
                project_id=session.project_id,
                version=2,
                is_current=True,
                source_filename="replacement.txt",
                media_type="text/plain",
                file_size=11,
                content_sha256="b" * 64,
                normalized_text="replacement resume text",
                structured_context_json={"projects": [{"id": "project-2", "summary": "替换后的项目"}]},
                parser_version="resume-v1",
                status=ResumeContextStatus.READY,
            )
        )
        db.commit()

        payload = _report_payload(db, report)
        assert payload["candidate_background"]["projects"][0]["summary"] == "图像项目"
        assert "project-2" not in str(payload["candidate_background"])
