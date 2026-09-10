from fastapi.testclient import TestClient

from backend.app.main import app


def test_chat_uses_safe_demo_fallback_without_api_key(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.services.llm.get_llm_api_key", lambda explicit=None: None)
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "对话测试"}).json()
        response = client.post(f"/api/projects/{project['id']}/chat", json={"message": "现在是什么状态？"})
        assert response.status_code == 200
        body = response.json()
        assert body["source"] == "demo-fallback"
        assert "对话测试" in body["reply"]


def test_chat_rejects_unknown_project() -> None:
    with TestClient(app) as client:
        response = client.post("/api/projects/missing/chat", json={"message": "你好"})
        assert response.status_code == 404


def test_remove_command_requires_confirmation_then_updates_jd() -> None:
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "命令测试"}).json()
        client.post(f"/api/projects/{project['id']}/jds/text", json={"title": "前端JD", "text": "负责 React 组件开发"})
        preview = client.post(f"/api/projects/{project['id']}/chat", json={"message": "请移除《前端JD》"}).json()
        assert preview["operation"]["requires_confirmation"] is True
        done = client.post(f"/api/projects/{project['id']}/chat", json={"message": "请移除《前端JD》", "confirm": True}).json()
        assert done["operation"]["action"] == "REMOVE_JD"
        analysis = client.get(f"/api/projects/{project['id']}/analysis").json()
        assert analysis["jds"][0]["participates_in_model"] is False


def test_chat_history_is_returned_for_project() -> None:
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "历史测试"}).json()
        client.post(f"/api/projects/{project['id']}/chat", json={"message": "当前进度如何？"})
        history = client.get(f"/api/projects/{project['id']}/chat/history")
        assert history.status_code == 200
        assert any(item["content"] == "当前进度如何？" for item in history.json()["messages"])


def test_chat_can_save_and_parse_a_pasted_jd() -> None:
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "对话导入 JD"}).json()
        message = "岗位名称：前端工程师\n岗位职责：负责 React 组件开发和页面性能优化，参与技术方案设计。\n任职要求：熟悉 TypeScript、React 和前端工程化。"
        response = client.post(f"/api/projects/{project['id']}/chat", json={"message": message})
        assert response.status_code == 200
        body = response.json()
        assert body["operation"]["action"] == "JD_INGESTED"
        assert any("已从对话保存 JD" in item for item in body["system_notices"])
        analysis = client.get(f"/api/projects/{project['id']}/analysis").json()
        assert analysis["jds"][0]["title"] == "前端工程师"
        assert analysis["jds"][0]["status"] == "COMPLETED"
        assert analysis["jds"][0]["competencies"]


def test_suspected_pasted_jd_requires_confirmation_before_saving() -> None:
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "疑似 JD"}).json()
        message = "这是一段岗位介绍。岗位职责包括 React 组件开发、页面性能优化和技术方案协作，欢迎熟悉 TypeScript 的候选人加入团队。"
        preview = client.post(f"/api/projects/{project['id']}/chat", json={"message": message}).json()
        assert preview["operation"]["action"] == "JD_INGESTED"
        assert preview["operation"]["requires_confirmation"] is True
        assert client.get(f"/api/projects/{project['id']}/analysis").json()["jds"] == []
        done = client.post(f"/api/projects/{project['id']}/chat", json={"message": message, "confirm": True}).json()
        assert done["operation"]["action"] == "JD_INGESTED"
        assert client.get(f"/api/projects/{project['id']}/analysis").json()["jds"][0]["status"] == "COMPLETED"


def test_public_link_extracts_page_text(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def read(self, *args): return b"<html><title>JD</title><body>React frontend engineer</body></html>"
    monkeypatch.setattr("backend.app.routes.jds.urlopen", lambda *args, **kwargs: FakeResponse())
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "网页 JD"}).json()
        response = client.post(f"/api/projects/{project['id']}/jds/link", json={"url": "https://example.com/job"})
        assert response.status_code == 201
        assert "React" in response.json()["raw_text"]


def test_browser_capture_is_analyzed_for_single_jd_model() -> None:
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "浏览器提取"}).json()
        response = client.post(f"/api/projects/{project['id']}/jds/browser", json={
            "page_title": "前端工程师",
            "url": "https://example.com/jobs/frontend",
            "extracted": {"job_title": "前端工程师", "description": "负责 React 组件开发和页面性能优化。"},
        })
        assert response.status_code == 201
        assert response.json()["status"] == "COMPLETED"
        analysis = client.get(f"/api/projects/{project['id']}/analysis").json()
        assert analysis["jds"][0]["competencies"]
        history = client.get(f"/api/projects/{project['id']}/chat/history").json()["messages"]
        assert any(item["role"] == "system" and "已从浏览器提取并保存 JD" in item["content"] for item in history)


def test_public_link_failure_explains_recognized_adapter(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.routes.jds.urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(OSError(10013, "socket denied")))
    with TestClient(app) as client:
        project = client.post(f"/api/projects", json={"name": "网页提取失败"}).json()
        response = client.post(f"/api/projects/{project['id']}/jds/link", json={"url": "https://www.zhipin.com/job_detail/123"})
        assert response.status_code == 502
        assert "Boss 直聘" in response.json()["detail"]
        assert "浏览器提取" in response.json()["detail"]
