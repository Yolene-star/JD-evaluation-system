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


def test_draft_competency_weight_keeps_requested_value_and_normalizes_siblings() -> None:
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "权重编辑测试"}).json()
        client.post(
            f"/api/projects/{project['id']}/jds/text",
            json={"title": "前端", "text": "负责 React 组件开发和页面性能优化"},
        )
        client.post(f"/api/projects/{project['id']}/analysis/run")
        competencies = client.get(f"/api/projects/{project['id']}/analysis").json()["jds"][0]["competencies"]
        target = next(item for item in competencies if item["name"] == "组件化开发")

        response = client.patch(f"/api/competencies/{target['id']}", json={"weight": 0.25})

        assert response.status_code == 200
        updated = client.get(f"/api/projects/{project['id']}/analysis").json()["jds"][0]["competencies"]
        weights = {item["name"]: item["weight"] for item in updated}
        assert abs(weights["组件化开发"] - 0.25) < 1e-9
        assert abs(sum(weights.values()) - 1.0) < 1e-9
