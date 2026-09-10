from fastapi.testclient import TestClient

from backend.app.main import app


def test_resolved_conflict_survives_model_reload_and_allows_confirmation() -> None:
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "冲突持久化"}).json()
        client.post(f"/api/projects/{project['id']}/jds/text", json={"title": "A", "text": "负责数据分析"})
        client.post(f"/api/projects/{project['id']}/jds/text", json={"title": "B", "text": "负责数据分析能力"})
        client.post(f"/api/projects/{project['id']}/analysis/run")
        draft = client.post(f"/api/projects/{project['id']}/aggregate").json()
        assert draft["conflict_count"] == 1
        resolved = client.post(f"/api/models/{draft['id']}/conflicts/0/resolve", json={"decision": "MERGE"})
        assert resolved.status_code == 200
        reloaded = client.get(f"/api/models/{draft['id']}").json()
        assert reloaded["conflict_count"] == 0
        assert client.post(f"/api/models/{draft['id']}/confirm").status_code == 201
