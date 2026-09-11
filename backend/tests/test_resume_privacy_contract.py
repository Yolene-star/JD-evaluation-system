from fastapi.testclient import TestClient

from backend.app.main import app


def test_resume_summary_does_not_expose_normalized_text():
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "privacy"}).json()
        response = client.post(
            f"/api/projects/{project['id']}/resume-context",
            files={"file": ("resume.txt", b"PROJECTS\nInternal project", "text/plain")},
        )
        assert response.status_code == 200
        body = response.json()
        assert "normalized_text" not in body
        assert "content" not in body
