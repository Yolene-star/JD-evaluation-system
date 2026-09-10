import json

from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.db import SessionLocal
from backend.app.main import app
from backend.app.models import ResumeContextStatus, ResumeContextVersion
from backend.app.services.resume_parser import MAX_RESUME_BYTES


def _project(client: TestClient, name: str = "简历上下文测试") -> dict:
    response = client.post("/api/projects", json={"name": name})
    assert response.status_code == 201
    return response.json()


def _upload(client: TestClient, project_id: str, filename: str, content: bytes) -> object:
    return client.post(
        f"/api/projects/{project_id}/resume-context",
        files={"file": (filename, content, "text/plain")},
    )


def test_uploading_resume_returns_redacted_structured_current_context() -> None:
    """Would fail if upload did not create a safe READY current version."""
    with TestClient(app) as client:
        project = _project(client)
        response = _upload(
            client,
            project["id"],
            "candidate.txt",
            b"PROJECTS\nSearch service\nEmail: candidate@example.com",
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["version"] == 1
        assert payload["status"] == "READY"
        assert payload["source_type"] == "BACKGROUND_ONLY"
        assert any("Search service" in item["summary"] for item in payload["projects"])
        assert "normalized_text" not in payload
        assert "candidate@example.com" not in json.dumps(payload)

        current = client.get(f"/api/projects/{project['id']}/resume-context")
        assert current.status_code == 200
        assert current.json()["id"] == payload["id"]


def test_replacing_resume_keeps_old_version_and_switches_current() -> None:
    """Would fail if replacement overwrote history or left the old version current."""
    with TestClient(app) as client:
        project = _project(client)
        first = _upload(client, project["id"], "first.txt", b"PROJECTS\nSearch service")
        second = _upload(client, project["id"], "second.txt", b"PROJECTS\nRanking service")

        assert first.status_code == second.status_code == 200
        assert second.json()["version"] == first.json()["version"] + 1
        assert client.get(f"/api/projects/{project['id']}/resume-context").json()["id"] == second.json()["id"]
        with SessionLocal() as db:
            versions = list(
                db.scalars(
                    select(ResumeContextVersion)
                    .where(ResumeContextVersion.project_id == project["id"])
                    .order_by(ResumeContextVersion.version)
                )
            )
        assert [(version.version, version.is_current) for version in versions] == [(1, False), (2, True)]


def test_failed_replacement_preserves_previous_ready_current_version() -> None:
    """Would fail if a failed parse cleared the usable current context."""
    with TestClient(app) as client:
        project = _project(client)
        first = _upload(client, project["id"], "first.txt", b"PROJECTS\nSearch service").json()
        failed = _upload(client, project["id"], "empty.txt", b"")

        assert failed.status_code == 422
        assert failed.json()["detail"] == "RESUME_EMPTY"
        current = client.get(f"/api/projects/{project['id']}/resume-context")
        assert current.status_code == 200
        assert current.json()["id"] == first["id"]
        with SessionLocal() as db:
            failed_version = db.scalar(
                select(ResumeContextVersion).where(
                    ResumeContextVersion.project_id == project["id"],
                    ResumeContextVersion.status == ResumeContextStatus.FAILED,
                )
            )
        assert failed_version is not None
        assert failed_version.is_current is False
        assert failed_version.failure_reason == "RESUME_EMPTY"


def test_upload_rejects_unsupported_and_oversized_files_with_project_not_found() -> None:
    """Would fail if unsafe uploads reached parsing or unknown projects gained records."""
    with TestClient(app) as client:
        project = _project(client)
        unsupported = client.post(
            f"/api/projects/{project['id']}/resume-context",
            files={"file": ("candidate.exe", b"not executable", "application/octet-stream")},
        )
        oversized = _upload(client, project["id"], "large.txt", b"a" * (MAX_RESUME_BYTES + 1))
        unknown = _upload(client, "missing-project", "candidate.txt", b"PROJECTS\nSafe")

        assert unsupported.status_code == 415
        assert oversized.status_code == 413
        assert unknown.status_code == 404


def test_cancel_and_project_isolation_leave_other_current_context_unchanged() -> None:
    """Would fail if cancel/read operations crossed their project boundary."""
    with TestClient(app) as client:
        first_project = _project(client, "第一个项目")
        second_project = _project(client, "第二个项目")
        first = _upload(client, first_project["id"], "first.txt", b"PROJECTS\nFirst project").json()
        second = _upload(client, second_project["id"], "second.txt", b"PROJECTS\nSecond project").json()

        assert client.get(f"/api/projects/{first_project['id']}/resume-context").json()["id"] == first["id"]
        assert client.get(f"/api/projects/{second_project['id']}/resume-context").json()["id"] == second["id"]
        cancelled = client.delete(f"/api/projects/{second_project['id']}/resume-context")
        assert cancelled.status_code == 204
        assert client.get(f"/api/projects/{second_project['id']}/resume-context").status_code == 404
        assert client.get(f"/api/projects/{first_project['id']}/resume-context").json()["id"] == first["id"]
        assert client.delete("/api/projects/missing-project/resume-context").status_code == 404
