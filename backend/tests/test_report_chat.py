from fastapi.testclient import TestClient

from backend.app.db import Base, SessionLocal, engine
from backend.app.main import app
from backend.app.models import AssessmentReport, AssessmentReportCompletion, AssessmentReportStatus, AssessmentSession, AssessmentSessionStatus, ModelVersion, Project, ReportNarrativeStatus, RubricSet, RubricSetStatus


def setup_function() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def _report() -> str:
    with SessionLocal() as db:
        project = Project(name="reports")
        db.add(project); db.flush()
        model = ModelVersion(project_id=project.id, version="v1", status="CONFIRMED")
        db.add(model); db.flush()
        session = AssessmentSession(project_id=project.id, model_version_id=model.id, status=AssessmentSessionStatus.PARTIALLY_FINISHED)
        db.add(session); db.flush()
        rubric = RubricSet(model_version_id=model.id, version="r1", status=RubricSetStatus.ACTIVE)
        db.add(rubric); db.flush()
        report = AssessmentReport(assessment_session_id=session.id, report_version=1, evidence_package_id="ep1", model_version_id=model.id, rubric_set_id=rubric.id, scoring_rule_version="stage3-v1", completion=AssessmentReportCompletion.PARTIAL, evaluated_weight=.5, unevaluated_weight=.5, match_score=70, match_score_type="PARTIAL", status=AssessmentReportStatus.READY, narrative_status=ReportNarrativeStatus.PENDING_RETRY)
        db.add(report); db.commit()
        return report.id


def test_report_chat_uses_llm_and_does_not_modify_score(monkeypatch) -> None:
    from backend.app.services import report_chat

    monkeypatch.setattr(
        report_chat,
        "_call_structured",
        lambda *args, **kwargs: report_chat.ReportChatResult(
            answer="根据当前报告，综合匹配度暂为 70；主要依据是已评价能力的加权结果。建议补充未评价能力的面试证据。",
            cited_evidence_ids=[],
        ),
    )
    with TestClient(app) as client:
        report_id = _report()
        response = client.post(f"/api/reports/{report_id}/chat/messages", json={"content": "为什么得到这个分数？"})
        assert response.status_code == 200
        assert "70" in response.json()["reply"]
        history = client.get(f"/api/reports/{report_id}/chat/messages").json()
        assert [item["role"] for item in history] == ["user", "agent"]
        assert client.get(f"/api/reports/{report_id}").json()["match_score"] == 70
