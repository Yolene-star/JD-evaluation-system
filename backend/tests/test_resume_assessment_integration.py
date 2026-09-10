from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.app.db import SessionLocal
from backend.app.main import app
from backend.app.models import AssessmentSession, ResumeSnapshot


def _confirmed_project(client: TestClient) -> dict:
    project = client.post("/api/projects", json={"name": "简历快照测评"}).json()
    client.post(
        f"/api/projects/{project['id']}/jds/text",
        json={"title": "工程师", "text": "负责 React 组件开发，优化页面性能"},
    )
    client.post(f"/api/projects/{project['id']}/analysis/run")
    model = client.post(f"/api/projects/{project['id']}/aggregate").json()
    client.post(f"/api/models/{model['id']}/confirm")
    return project


def _upload_resume(client: TestClient, project_id: str, filename: str, content: bytes) -> dict:
    response = client.post(
        f"/api/projects/{project_id}/resume-context",
        files={"file": (filename, content, "text/plain")},
    )
    assert response.status_code == 200
    return response.json()


def test_opted_in_session_freezes_current_resume_and_replacement_does_not_change_it() -> None:
    """Would fail if opted-in sessions did not persist their own current-resume snapshot."""
    with TestClient(app) as client:
        project = _confirmed_project(client)
        first = _upload_resume(client, project["id"], "first.txt", b"PROJECTS\nFirst project")
        old_session = client.post(
            f"/api/projects/{project['id']}/assessments",
            json={"use_resume_context": True},
        ).json()
        second = _upload_resume(client, project["id"], "second.txt", b"PROJECTS\nSecond project")
        new_session = client.post(
            f"/api/projects/{project['id']}/assessments",
            json={"use_resume_context": True},
        ).json()

        assert old_session["resume_context"]["version_id"] == first["id"]
        assert new_session["resume_context"]["version_id"] == second["id"]
        assert old_session["resume_context"]["snapshot_id"] != new_session["resume_context"]["snapshot_id"]

        with SessionLocal() as db:
            old_snapshot = db.scalar(
                select(ResumeSnapshot).where(ResumeSnapshot.session_id == old_session["id"])
            )
            assert old_snapshot is not None
            assert old_snapshot.snapshot_json["background"]["projects"][0]["summary"] == "First project"


def test_omitted_or_false_resume_option_creates_no_snapshot() -> None:
    """Would fail if the backward-compatible default created a resume snapshot."""
    with TestClient(app) as client:
        project = _confirmed_project(client)
        _upload_resume(client, project["id"], "resume.txt", b"PROJECTS\nOptional project")
        omitted = client.post(f"/api/projects/{project['id']}/assessments")
        disabled = client.post(
            f"/api/projects/{project['id']}/assessments",
            json={"use_resume_context": False},
        )

        assert omitted.status_code == disabled.status_code == 200
        assert omitted.json()["resume_context"] is None
        assert disabled.json()["resume_context"] is None
        with SessionLocal() as db:
            assert db.scalar(
                select(func.count()).select_from(ResumeSnapshot).where(
                    ResumeSnapshot.session_id.in_([omitted.json()["id"], disabled.json()["id"]])
                )
            ) == 0


def test_opted_in_session_without_ready_resume_returns_409_and_rolls_back() -> None:
    """Would fail if an unavailable context left behind a half-created assessment session."""
    with TestClient(app) as client:
        project = _confirmed_project(client)
        with SessionLocal() as db:
            before = db.scalar(
                select(func.count()).select_from(AssessmentSession).where(
                    AssessmentSession.project_id == project["id"]
                )
            )

        response = client.post(
            f"/api/projects/{project['id']}/assessments",
            json={"use_resume_context": True},
        )

        assert response.status_code == 409
        assert response.json()["detail"] == "RESUME_CONTEXT_NOT_AVAILABLE"
        with SessionLocal() as db:
            after = db.scalar(
                select(func.count()).select_from(AssessmentSession).where(
                    AssessmentSession.project_id == project["id"]
                )
            )
        assert after == before


def test_sessions_expose_no_resume_rebind_endpoint_before_or_after_start() -> None:
    """Would fail if a session could bind or replace a resume after it was created."""
    with TestClient(app) as client:
        project = _confirmed_project(client)
        _upload_resume(client, project["id"], "resume.txt", b"PROJECTS\nFixed background")
        session = client.post(
            f"/api/projects/{project['id']}/assessments",
            json={"use_resume_context": True},
        ).json()

        before_start = client.post(f"/api/assessments/{session['id']}/resume-context")
        assert before_start.status_code == 404
        assert client.post(f"/api/assessments/{session['id']}/start").status_code == 200
        after_start = client.post(f"/api/assessments/{session['id']}/resume-context")
        assert after_start.status_code == 404
