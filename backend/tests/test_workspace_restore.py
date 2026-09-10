from fastapi.testclient import TestClient

from backend.app.main import app


def test_latest_model_can_restore_workspace_after_reload() -> None:
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "恢复工作台"}).json()
        client.post(f"/api/projects/{project['id']}/jds/text", json={"title": "前端", "text": "负责 React 组件开发"})
        client.post(f"/api/projects/{project['id']}/analysis/run")
        draft = client.post(f"/api/projects/{project['id']}/aggregate").json()
        response = client.get(f"/api/projects/{project['id']}/models/latest")
        assert response.status_code == 200
        assert response.json()["id"] == draft["id"]


def test_delete_project_removes_it_from_history_without_touching_other_projects() -> None:
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "待删除任务"}).json()
        keep = client.post("/api/projects", json={"name": "保留任务"}).json()
        response = client.delete(f"/api/projects/{project['id']}")
        assert response.status_code == 204
        projects = client.get("/api/projects").json()
        assert project["id"] not in {item["id"] for item in projects}
        assert keep["id"] in {item["id"] for item in projects}
