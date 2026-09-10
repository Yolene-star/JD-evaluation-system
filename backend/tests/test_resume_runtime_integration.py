from fastapi.testclient import TestClient

from backend.app.main import app


def test_runtime_exposes_resume_context_and_report_background_contract() -> None:
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "运行时简历入口"}).json()
        upload = client.post(
            f"/api/projects/{project['id']}/resume-context",
            files={"file": ("resume.txt", b"PROJECTS\nA project", "text/plain")},
        )
        assert upload.status_code == 200
        response = client.get(f"/api/projects/{project['id']}/resume-context")
        assert response.status_code == 200


def test_assessment_create_accepts_resume_opt_in_field() -> None:
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "运行时测评"}).json()
        response = client.post(
            f"/api/projects/{project['id']}/assessments",
            json={"use_resume_context": False},
        )
        assert response.status_code != 404
