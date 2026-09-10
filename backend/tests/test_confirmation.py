from fastapi.testclient import TestClient

from backend.app.main import app


def _draft(client: TestClient) -> dict:
    project = client.post("/api/projects", json={"name": "冻结测试"}).json()
    client.post(f"/api/projects/{project['id']}/jds/text", json={"title": "前端", "text": "负责 React 组件开发"})
    client.post(f"/api/projects/{project['id']}/analysis/run")
    return client.post(f"/api/projects/{project['id']}/aggregate").json()


def test_confirmation_creates_immutable_snapshot_and_export() -> None:
    with TestClient(app) as client:
        draft = _draft(client)
        response = client.post(f"/api/models/{draft['id']}/confirm")
        assert response.status_code == 201
        assert response.json()["version"] == "v1.0"
        exported = client.get(f"/api/models/{draft['id']}/export")
        assert exported.status_code == 200
        assert exported.json()["version"] == "v1.0"


def test_confirmed_model_cannot_be_confirmed_again() -> None:
    with TestClient(app) as client:
        draft = _draft(client)
        client.post(f"/api/models/{draft['id']}/confirm")
        response = client.post(f"/api/models/{draft['id']}/confirm")
        assert response.status_code == 409


def test_confirmation_is_blocked_when_model_has_conflicts() -> None:
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "冲突测试"}).json()
        client.post(f"/api/projects/{project['id']}/jds/text", json={"title": "A", "text": "负责数据分析"})
        client.post(f"/api/projects/{project['id']}/jds/text", json={"title": "B", "text": "负责数据分析能力"})
        client.post(f"/api/projects/{project['id']}/analysis/run")
        draft = client.post(f"/api/projects/{project['id']}/aggregate").json()
        response = client.post(f"/api/models/{draft['id']}/confirm")
        assert response.status_code == 409
