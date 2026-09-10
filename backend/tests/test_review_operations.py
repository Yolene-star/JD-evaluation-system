from fastapi.testclient import TestClient

from backend.app.main import app


def test_readd_removed_jd_restores_participation() -> None:
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "恢复测试"}).json()
        jd = client.post(f"/api/projects/{project['id']}/jds/text", json={"title": "前端", "text": "负责 React 组件开发"}).json()
        client.patch(f"/api/jds/{jd['id']}", json={"participates_in_model": False})
        response = client.post(f"/api/jds/{jd['id']}/readd")
        assert response.status_code == 200
        assert response.json()["participates_in_model"] is True


def test_draft_competency_can_be_renamed() -> None:
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "编辑测试"}).json()
        jd = client.post(f"/api/projects/{project['id']}/jds/text", json={"title": "前端", "text": "负责 React 组件开发"}).json()
        client.post(f"/api/projects/{project['id']}/analysis/run")
        analysis = client.get(f"/api/projects/{project['id']}/analysis").json()
        competency_id = analysis["jds"][0]["competencies"][0]["id"]
        response = client.patch(f"/api/competencies/{competency_id}", json={"name": "组件工程"})
        assert response.status_code == 200
        assert response.json()["name"] == "组件工程"
