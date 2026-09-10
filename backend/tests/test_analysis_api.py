from fastapi.testclient import TestClient

from backend.app.main import app


def test_analysis_persists_evidence_and_competencies() -> None:
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "解析测试"}).json()
        jd = client.post(f"/api/projects/{project['id']}/jds/text", json={"title": "前端", "text": "负责 React 组件开发，优化页面性能"}).json()
        result = client.post(f"/api/projects/{project['id']}/analysis/run")
        assert result.status_code == 200
        assert result.json()["project_status"] == "REVIEWING"
        analysis = client.get(f"/api/projects/{project['id']}/analysis").json()
        row = next(item for item in analysis["jds"] if item["id"] == jd["id"])
        assert {item["name"] for item in row["competencies"]} == {"组件化开发", "性能优化"}
        assert len(row["evidence"]) == 2
