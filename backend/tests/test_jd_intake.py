from fastapi.testclient import TestClient

from backend.app.main import app


def test_text_jd_creates_audited_record() -> None:
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "产品岗位模型"}).json()
        response = client.post(
            f"/api/projects/{project['id']}/jds/text",
            json={"title": "前端JD", "text": "负责 React 组件开发"},
        )
        assert response.status_code == 201
        assert response.json()["status"] == "RECEIVED"
        events = client.get(f"/api/projects/{project['id']}/events").json()
        assert events[0]["action"] == "JD_ADDED"


def test_projects_are_ordered_by_recent_update() -> None:
    with TestClient(app) as client:
        first = client.post("/api/projects", json={"name": "旧任务"}).json()
        client.post("/api/projects", json={"name": "新任务"})
        projects = client.get("/api/projects").json()
        assert projects[0]["name"] == "新任务"
        assert any(item["id"] == first["id"] for item in projects)


def test_retry_endpoint_matches_frontend_button_path() -> None:
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "重试路径"}).json()
        jd = client.post(
            f"/api/projects/{project['id']}/jds/text",
            json={"title": "失败 JD", "text": "负责数据分析"},
        ).json()
        response = client.post(f"/api/jds/{jd['id']}/retry")
        assert response.status_code == 200
        assert response.json()["id"] == jd["id"]

def test_jd_title_can_be_renamed() -> None:
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "岗位改名"}).json()
        jd = client.post(f"/api/projects/{project['id']}/jds/text", json={"title": "旧岗位名", "text": "负责前端开发"}).json()
        response = client.patch(f"/api/jds/{jd['id']}", json={"title": "高级前端工程师"})
        assert response.status_code == 200
        assert response.json()["title"] == "高级前端工程师"
        events = client.get(f"/api/projects/{project['id']}/events").json()
        assert '"title": "高级前端工程师"' in events[0]["payload"]
