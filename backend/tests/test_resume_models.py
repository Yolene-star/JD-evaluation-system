import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db import Base
from backend.app.models import (
    AssessmentSession,
    ModelVersion,
    Project,
    ResumeContextStatus,
    ResumeContextVersion,
    ResumeSnapshot,
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


@pytest.fixture
def db():
    with TestSessionLocal() as session:
        yield session


@pytest.fixture
def project(db):
    project = Project(name="resume test")
    db.add(project)
    db.flush()
    return project


@pytest.fixture
def session(db, project):
    model = ModelVersion(project_id=project.id, version="v1")
    db.add(model)
    db.flush()
    assessment_session = AssessmentSession(project_id=project.id, model_version_id=model.id)
    db.add(assessment_session)
    db.flush()
    return assessment_session


def _version(project_id: str, version: int = 1, *, status: ResumeContextStatus = ResumeContextStatus.READY):
    return ResumeContextVersion(
        project_id=project_id,
        version=version,
        is_current=True,
        source_filename="resume.pdf",
        media_type="application/pdf",
        file_size=128,
        content_sha256="a" * 64,
        normalized_text="项目经历",
        structured_context_json={"projects": [], "education": [], "skills": [], "experiences": [], "summary": "", "source_segments": []},
        parser_version="resume-v1",
        status=status,
    )


def test_resume_snapshot_is_session_scoped_and_immutable(db, project, session):
    version = _version(project.id)
    db.add(version)
    db.flush()
    snapshot = ResumeSnapshot(
        session_id=session.id,
        resume_context_version_id=version.id,
        snapshot_json={"source_type": "BACKGROUND_ONLY", "projects": []},
    )
    db.add(snapshot)
    db.commit()

    snapshot.snapshot_json = {"source_type": "BACKGROUND_ONLY", "projects": [{"id": "changed"}]}
    with pytest.raises(ValueError, match="immutable"):
        db.commit()


def test_resume_snapshot_session_id_is_unique(db, project, session):
    version = _version(project.id)
    db.add(version)
    db.flush()
    db.add_all(
        [
            ResumeSnapshot(session_id=session.id, resume_context_version_id=version.id, snapshot_json={}),
            ResumeSnapshot(session_id=session.id, resume_context_version_id=version.id, snapshot_json={}),
        ]
    )
    with pytest.raises(IntegrityError):
        db.commit()


def test_resume_version_status_changes_do_not_delete_snapshot(db, project, session):
    version = _version(project.id)
    db.add(version)
    db.flush()
    snapshot = ResumeSnapshot(session_id=session.id, resume_context_version_id=version.id, snapshot_json={"source_type": "BACKGROUND_ONLY"})
    db.add(snapshot)
    db.commit()

    version.status = ResumeContextStatus.FAILED
    version.is_current = False
    version.failure_reason = "parse failed"
    db.commit()

    assert db.get(ResumeSnapshot, snapshot.id) is not None


def test_resume_snapshot_delete_is_rejected(db, project, session):
    version = _version(project.id)
    db.add(version)
    db.flush()
    snapshot = ResumeSnapshot(session_id=session.id, resume_context_version_id=version.id, snapshot_json={})
    db.add(snapshot)
    db.commit()

    db.delete(snapshot)
    with pytest.raises(ValueError, match="immutable"):
        db.commit()
