from fastapi.testclient import TestClient

from backend.app.main import app


def test_stage_one_invariants_hold_for_confirmed_snapshot() -> None:
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "阶段一验收"}).json()
        jd = client.post(f"/api/projects/{project['id']}/jds/text", json={"title": "前端", "text": "负责 React 组件开发，优化页面性能"}).json()
        client.post(f"/api/projects/{project['id']}/analysis/run")
        draft = client.post(f"/api/projects/{project['id']}/aggregate").json()
        assert sum(row["weight"] for row in draft["competencies"]) == 1
        assert all(row["evidence_ids"] for row in draft["competencies"])
        confirmed = client.post(f"/api/models/{draft['id']}/confirm")
        assert confirmed.status_code == 201
        assert client.patch(f"/api/jds/{jd['id']}", json={"title": "修改后"}).status_code == 200
        assert client.patch(f"/api/competencies/{draft['competencies'][0].get('id', '')}", json={"name": "不应修改"}).status_code in {404, 409}
        events = client.get(f"/api/projects/{project['id']}/events").json()
        assert {event["action"] for event in events} >= {"JD_ADDED", "ANALYSIS_COMPLETED", "MODEL_AGGREGATED", "MODEL_CONFIRMED"}


def test_retry_does_not_duplicate_jd_record() -> None:
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "重试幂等"}).json()
        jd = client.post(f"/api/projects/{project['id']}/jds/text", json={"title": "岗位", "text": "负责 React 组件开发"}).json()
        client.post(f"/api/jds/{jd['id']}/retry")
        client.post(f"/api/jds/{jd['id']}/retry")
        analysis = client.get(f"/api/projects/{project['id']}/analysis").json()
        assert [item["id"] for item in analysis["jds"]].count(jd["id"]) == 1
