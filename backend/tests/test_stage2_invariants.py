from sqlalchemy import func, select
from fastapi.testclient import TestClient

from backend.app.db import SessionLocal
from backend.app.main import app
from backend.app.models import AssessmentTurn, AssessmentSession, ModelVersion
from backend.app.services.assessment_ai import AnalysisResult


def _confirmed_project(client: TestClient) -> dict:
    project = client.post("/api/projects", json={"name": "阶段二不变量"}).json()
    client.post(
        f"/api/projects/{project['id']}/jds/text",
        json={"title": "工程师", "text": "负责 React 组件开发，优化页面性能"},
    )
    client.post(f"/api/projects/{project['id']}/analysis/run")
    model = client.post(f"/api/projects/{project['id']}/aggregate").json()
    assert client.post(f"/api/models/{model['id']}/confirm").status_code == 201
    return {**project, "model_version_id": model["id"]}


def test_session_never_exceeds_two_followups(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.services.assessment_ai.get_llm_api_key", lambda: None)
    monkeypatch.setattr(
        "backend.app.services.assessment_service.analyze_answer",
        lambda *_args, **_kwargs: AnalysisResult(
            answer_summary="信息不足",
            evidence=[],
            evidence_sufficiency="INSUFFICIENT",
            needs_follow_up=True,
            follow_up_reason="请补充背景和结果",
            follow_up_question="请补充背景和结果",
        ),
    )
    with TestClient(app) as client:
        project = _confirmed_project(client)
        session = client.post(f"/api/projects/{project['id']}/assessments").json()
        client.post(f"/api/assessments/{session['id']}/start")
        for index in range(4):
            response = client.post(
                f"/api/assessments/{session['id']}/turns",
                json={"content": "不足", "idempotency_key": f"insufficient-{index}"},
            )
            if response.status_code == 409:
                break
        state = client.get(f"/api/assessments/{session['id']}").json()
        assert all(item["follow_up_count"] <= 2 for item in state["competencies"])


def test_duplicate_idempotency_key_creates_one_answer_record(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.services.assessment_ai.get_llm_api_key", lambda: None)
    with TestClient(app) as client:
        project = _confirmed_project(client)
        session = client.post(f"/api/projects/{project['id']}/assessments").json()
        client.post(f"/api/assessments/{session['id']}/start")
        payload = {"content": "我负责过组件开发", "idempotency_key": "same-answer"}
        first = client.post(f"/api/assessments/{session['id']}/turns", json=payload)
        second = client.post(f"/api/assessments/{session['id']}/turns", json=payload)
        assert first.status_code == second.status_code == 200
        assert first.json() == second.json()
        with SessionLocal() as db:
            count = db.scalar(
                select(func.count()).select_from(AssessmentTurn).where(
                    AssessmentTurn.session_id == session["id"],
                    AssessmentTurn.idempotency_key == "same-answer",
                )
            )
        assert count == 1


def test_session_keeps_confirmed_model_version_reference(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.services.assessment_ai.get_llm_api_key", lambda: None)
    with TestClient(app) as client:
        project = _confirmed_project(client)
        session = client.post(f"/api/projects/{project['id']}/assessments").json()
        with SessionLocal() as db:
            model = db.get(ModelVersion, project["model_version_id"])
            assert model is not None
            model.version = "tampered-label"
            db.commit()
        snapshot = client.get(f"/api/assessments/{session['id']}").json()
        assert snapshot["model_version_id"] == project["model_version_id"]


def test_event_sequence_and_full_package_are_traceable(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.services.assessment_ai.get_llm_api_key", lambda: None)
    monkeypatch.setattr(
        "backend.app.services.assessment_service.analyze_answer",
        lambda *_args, **_kwargs: AnalysisResult(
            answer_summary="有项目经历",
            evidence=[],
            evidence_sufficiency="SUFFICIENT",
            needs_follow_up=False,
        ),
    )
    with TestClient(app) as client:
        project = _confirmed_project(client)
        session = client.post(f"/api/projects/{project['id']}/assessments").json()
        client.post(f"/api/assessments/{session['id']}/start")
        answer = client.post(
            f"/api/assessments/{session['id']}/turns",
            json={"content": "我完成过 React 组件开发并优化性能", "idempotency_key": "complete-1"},
        )
        assert answer.status_code == 200
        events = client.get(f"/api/assessments/{session['id']}/events").json()
        actions = [event["action"] for event in events]
        assert actions[0] == "ASSESSMENT_CREATED"
        assert "ASSESSMENT_STARTED" in actions
        assert "ANSWER_SUBMITTED" in actions
        assert "ANSWER_ANALYZED" in actions
        state = client.get(f"/api/assessments/{session['id']}").json()
        if state["status"] == "COMPLETED":
            assert "ASSESSMENT_COMPLETED" in actions
            package = client.get(f"/api/assessments/{session['id']}/evidence-package")
            assert package.status_code == 200
            assert package.json()["completion"] == "FULL"
            assert "score" not in package.json()


def test_partial_package_is_traceable_and_has_no_stage_three_fields() -> None:
    with TestClient(app) as client:
        project = _confirmed_project(client)
        session = client.post(f"/api/projects/{project['id']}/assessments").json()
        client.post(f"/api/assessments/{session['id']}/start")
        finished = client.post(
            f"/api/assessments/{session['id']}/finish",
            json={"confirm": True, "reason": "暂时结束"},
        )
        assert finished.status_code == 200
        package = client.get(f"/api/assessments/{session['id']}/evidence-package")
        assert package.status_code == 200
        body = package.json()
        assert body["completion"] == "PARTIAL"
        assert "score" not in body and "radar" not in body and "profile" not in body
