from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.db import SessionLocal
from backend.app.main import app
from backend.app.models import LLMCallLog
from backend.app.services.parsing import ParsedCompetency, ParsedJd


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


def test_analysis_uses_validated_llm_result_and_records_call(monkeypatch) -> None:
    parsed = ParsedJd(
        competencies=(ParsedCompetency(
            name="智能体后端开发",
            evidence_ids=(),
            excerpt="参与智能体产品的后端开发工作",
            start_offset=0,
            end_offset=15,
            description="设计并实现智能体后端模块",
        ),),
        qualifications=("本科",),
        constraints=(),
    )
    monkeypatch.setenv("LLM_ANALYSIS_ENABLED", "1")
    monkeypatch.setattr(
        "backend.app.services.analysis.parse_jd_with_llm",
        lambda text: (parsed, "llm", 23, None),
    )

    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "AI 解析测试"}).json()
        client.post(
            f"/api/projects/{project['id']}/jds/text",
            json={"title": "智能体开发", "text": "参与智能体产品的后端开发工作，要求本科。"},
        )
        response = client.post(f"/api/projects/{project['id']}/analysis/run")
        assert response.status_code == 200
        row = client.get(f"/api/projects/{project['id']}/analysis").json()["jds"][0]
        assert row["competencies"][0]["description"] == "设计并实现智能体后端模块"

    with SessionLocal() as db:
        log = db.scalars(
            select(LLMCallLog)
            .where(LLMCallLog.project_id == project["id"])
            .order_by(LLMCallLog.id.desc())
        ).first()
        assert log is not None
        assert log.task_type == "stage1-jd-analysis"
        assert log.status == "llm"
        assert log.latency_ms == 23


def test_empty_ai_result_marks_jd_failed_without_erasing_previous_model(monkeypatch) -> None:
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "空结果保护"}).json()
        jd = client.post(
            f"/api/projects/{project['id']}/jds/text",
            json={"title": "前端", "text": "岗位职责：负责 React 组件开发和前端工程化建设。"},
        ).json()
        client.post(f"/api/projects/{project['id']}/analysis/run")
        before = client.get(f"/api/projects/{project['id']}/analysis").json()["jds"][0]
        assert before["competencies"]

        monkeypatch.setenv("LLM_ANALYSIS_ENABLED", "1")
        monkeypatch.setattr(
            "backend.app.services.analysis.parse_jd_with_llm",
            lambda text: (ParsedJd(competencies=(), qualifications=(), constraints=()), "deterministic-fallback", 8, "没有有效能力"),
        )
        client.post(f"/api/projects/{project['id']}/analysis/run")
        after = client.get(f"/api/projects/{project['id']}/analysis").json()["jds"][0]

        assert after["id"] == jd["id"]
        assert after["status"] == "FAILED"
        assert after["competencies"] == before["competencies"]
