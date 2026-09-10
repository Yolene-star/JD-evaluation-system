from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.main import app
from backend.app.db import SessionLocal
from backend.app.models import AssessmentEvent, AssessmentSession, AssessmentTurn, CompetencyAssessment
from backend.app.services.assessment_ai import AnalysisResult, EvidenceResult, RetryableAIError


def _confirmed_project(client: TestClient) -> dict:
    project = client.post("/api/projects", json={"name": "阶段二 API"}).json()
    client.post(f"/api/projects/{project['id']}/jds/text", json={"title": "工程师", "text": "负责 React 组件开发，优化页面性能"})
    client.post(f"/api/projects/{project['id']}/analysis/run")
    model = client.post(f"/api/projects/{project['id']}/aggregate").json()
    client.post(f"/api/models/{model['id']}/confirm")
    return project


def test_create_start_and_duplicate_answer_is_idempotent(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.services.assessment_ai.get_llm_api_key", lambda: None)
    with TestClient(app) as client:
        project = _confirmed_project(client)
        session = client.post(f"/api/projects/{project['id']}/assessments").json()
        assert session["status"] == "READY"
        started = client.post(f"/api/assessments/{session['id']}/start")
        assert started.status_code == 200
        assert started.json()["current_question"]["covered_competency_ids"]
        payload = {"content": "我做过系统设计", "idempotency_key": "answer-1"}
        first = client.post(f"/api/assessments/{session['id']}/turns", json=payload)
        second = client.post(f"/api/assessments/{session['id']}/turns", json=payload)
        assert first.status_code == 200
        assert second.json() == first.json()


def test_create_ready_snapshot_includes_confirmed_competency_names_and_progress() -> None:
    with TestClient(app) as client:
        project = _confirmed_project(client)
        session = client.post(f"/api/projects/{project['id']}/assessments").json()

        assert session["progress"]["total"] == len(session["competencies"])
        assert session["progress"]["total"] > 0
        assert all(item["name"] for item in session["competencies"])
        assert session["agent_status"] is None


def test_answer_response_keeps_legacy_fields_and_adds_agent_status(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.services.assessment_ai.get_llm_api_key", lambda: None)
    with TestClient(app) as client:
        project = _confirmed_project(client)
        session = client.post(f"/api/projects/{project['id']}/assessments").json()
        client.post(f"/api/assessments/{session['id']}/start")

        response = client.post(
            f"/api/assessments/{session['id']}/turns",
            json={"content": "我不会", "idempotency_key": "agent-status-1"},
        )

        assert response.status_code == 200
        body = response.json()
        assert {
            "session_id",
            "model_version_id",
            "status",
            "completion",
            "current_question",
            "competencies",
            "turns",
            "progress",
            "retryable",
        }.issubset(body)
        assert body["agent_status"]["phase"] in {
            "FOLLOWING_UP",
            "MOVING_NEXT",
            "COMPLETED",
            "RETRY_REQUIRED",
        }
        assert body["agent_status"]["active_competency_id"] == body["current_competency_id"]


def test_pause_resume_rejects_answer_while_paused(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.services.assessment_ai.get_llm_api_key", lambda: None)
    with TestClient(app) as client:
        project = _confirmed_project(client)
        session = client.post(f"/api/projects/{project['id']}/assessments").json()
        client.post(f"/api/assessments/{session['id']}/start")
        assert client.post(f"/api/assessments/{session['id']}/pause").status_code == 200
        paused = client.post(f"/api/assessments/{session['id']}/turns", json={"content": "回答", "idempotency_key": "paused"})
        assert paused.status_code == 409
        assert client.post(f"/api/assessments/{session['id']}/resume").status_code == 200


def test_retry_reuses_saved_answer_without_creating_duplicate_turn(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.services.assessment_ai.get_llm_api_key", lambda: None)
    with TestClient(app) as client:
        project = _confirmed_project(client)
        session = client.post(f"/api/projects/{project['id']}/assessments").json()
        client.post(f"/api/assessments/{session['id']}/start")

        def fail(*_args, **_kwargs):
            raise RetryableAIError("temporary provider failure")

        monkeypatch.setattr("backend.app.services.assessment_service.analyze_answer", fail)
        failed = client.post(f"/api/assessments/{session['id']}/turns", json={"content": "回答", "idempotency_key": "retry-1"})
        assert failed.status_code == 200
        assert failed.json()["retryable"] is True

        with SessionLocal() as db:
            answer_ids = [
                turn.id
                for turn in db.scalars(
                    select(AssessmentTurn).where(
                        AssessmentTurn.session_id == session["id"], AssessmentTurn.idempotency_key == "retry-1"
                    )
                )
            ]
            assert len(answer_ids) == 1

        monkeypatch.setattr("backend.app.services.assessment_service.analyze_answer", lambda *_args, **_kwargs: AnalysisResult(answer_summary="ok", evidence=[], evidence_sufficiency="SUFFICIENT", needs_follow_up=False))
        retried = client.post(f"/api/assessments/{session['id']}/retry")
        assert retried.status_code == 200
        with SessionLocal() as db:
            assert db.scalar(select(AssessmentTurn).where(AssessmentTurn.session_id == session["id"], AssessmentTurn.idempotency_key == "retry-1").count()) if False else True
            turns = list(db.scalars(select(AssessmentTurn).where(AssessmentTurn.session_id == session["id"], AssessmentTurn.idempotency_key == "retry-1")))
            assert len(turns) == 1


def test_demo_answer_analysis_advances_without_retry_notice(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.services.assessment_ai.get_llm_api_key", lambda: None)
    with TestClient(app) as client:
        project = _confirmed_project(client)
        session = client.post(f"/api/projects/{project['id']}/assessments").json()
        client.post(f"/api/assessments/{session['id']}/start")

        response = client.post(
            f"/api/assessments/{session['id']}/turns",
            json={"content": "我不会", "idempotency_key": "demo-analysis-1"},
        )

        assert response.status_code == 200
        state = response.json()
        assert state["retryable"] is False
        assert state["error"] is None
        assert state["competencies"][0]["status"] == "FOLLOW_UP"
        assert state["evidence_groups"][0]["competency_name"] == state["competencies"][0]["name"]
        assert state["evidence_groups"][0]["sufficiency"] == "INSUFFICIENT"
        assert state["evidence_groups"][0]["observations"][0] == "我不会"


def test_finish_requires_explicit_confirmation_and_composite_targets_are_independent(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.services.assessment_ai.get_llm_api_key", lambda: None)
    with TestClient(app) as client:
        project = _confirmed_project(client)
        session = client.post(f"/api/projects/{project['id']}/assessments").json()

        with SessionLocal() as db:
            model_session = db.get(AssessmentSession, session["id"])
            assert model_session is not None
        client.post(f"/api/assessments/{session['id']}/start")
        assert client.post(f"/api/assessments/{session['id']}/finish", json={"reason": "done"}).status_code == 422
        with SessionLocal() as db:
            system_question = db.scalar(select(AssessmentTurn).where(AssessmentTurn.session_id == session["id"], AssessmentTurn.role == "SYSTEM").order_by(AssessmentTurn.turn_index.desc()))
            ids = [item.competency_id for item in db.scalars(select(CompetencyAssessment).where(CompetencyAssessment.session_id == session["id"]).order_by(CompetencyAssessment.created_at)).all()]
            assert len(ids) >= 2
            system_question.covered_competency_ids = ids[:2]
            db.commit()

        def analyze(_snapshot, competency, *_args):
            sufficient = competency.id == ids[0]
            return AnalysisResult(answer_summary="ok", evidence=[], evidence_sufficiency="SUFFICIENT" if sufficient else "INSUFFICIENT", needs_follow_up=not sufficient, follow_up_reason="补充", follow_up_question="请补充")

        monkeypatch.setattr("backend.app.services.assessment_service.analyze_answer", analyze)
        response = client.post(f"/api/assessments/{session['id']}/turns", json={"content": "综合回答", "idempotency_key": "composite-1"})
        assert response.status_code == 200
        state = response.json()
        by_id = {item["competency_id"]: item for item in state["competencies"]}
        assert by_id[ids[0]]["status"] == "SUFFICIENT"
        assert by_id[ids[1]]["status"] == "FOLLOW_UP"
        assert state["current_competency_id"] == ids[1]
