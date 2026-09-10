from fastapi.testclient import TestClient
from backend.app.db import SessionLocal
from backend.app.models import (
    AssessmentSession,
    AssessmentSessionStatus,
    AssessmentTurn,
    AssessmentTurnRole,
    AssessmentTurnType,
    CompetencyAssessment,
    CompetencyAssessmentEvidenceSufficiency,
    CompetencyAssessmentStatus,
    EvidenceObservation,
    EvidenceType,
    ModelVersion,
    ModelVersionStatus,
    Project,
    AssessmentCompletion,
)
from backend.app.services.evidence_package import build_evidence_package

from backend.app.main import app


def test_evidence_package_rejects_non_terminal_session() -> None:
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "证据包"}).json()
        client.post(f"/api/projects/{project['id']}/jds/text", json={"title": "前端", "text": "负责 React 组件开发"})
        client.post(f"/api/projects/{project['id']}/analysis/run")
        model = client.post(f"/api/projects/{project['id']}/aggregate").json()
        client.post(f"/api/models/{model['id']}/confirm")
        session = client.post(f"/api/projects/{project['id']}/assessments").json()
        response = client.get(f"/api/assessments/{session['id']}/evidence-package")
        assert response.status_code == 409


def _persist_terminal_session(status: AssessmentSessionStatus) -> str:
    db = SessionLocal()
    project = Project(name="证据包 fixture")
    db.add(project)
    db.flush()
    model = ModelVersion(project_id=project.id, status=ModelVersionStatus.CONFIRMED, version="v1.0")
    db.add(model)
    db.flush()
    session = AssessmentSession(
        project_id=project.id,
        model_version_id=model.id,
        status=status,
        completion=AssessmentCompletion.FULL if status is AssessmentSessionStatus.COMPLETED else AssessmentCompletion.PARTIAL,
    )
    db.add(session)
    db.flush()
    competency = CompetencyAssessment(
        session_id=session.id,
        competency_id="snapshot-c1",
        status=CompetencyAssessmentStatus.SUFFICIENT if status is AssessmentSessionStatus.COMPLETED else CompetencyAssessmentStatus.INCOMPLETE,
        evidence_sufficiency=CompetencyAssessmentEvidenceSufficiency.SUFFICIENT if status is AssessmentSessionStatus.COMPLETED else CompetencyAssessmentEvidenceSufficiency.UNCERTAIN,
    )
    db.add(competency)
    db.flush()
    turn = AssessmentTurn(
        session_id=session.id,
        competency_assessment_id=competency.id,
        turn_index=1,
        role=AssessmentTurnRole.USER,
        turn_type=AssessmentTurnType.ANSWER,
        content="我负责过容量评估并推动上线。",
        covered_competency_ids=["snapshot-c1"],
        idempotency_key=f"fixture-{session.id}",
    )
    db.add(turn)
    db.flush()
    db.add(EvidenceObservation(
        session_id=session.id,
        competency_assessment_id=competency.id,
        competency_id="snapshot-c1",
        turn_id=turn.id,
        evidence_type=EvidenceType.POSITIVE,
        excerpt="容量评估",
        source_excerpt="容量评估",
        summary="有相关项目经历",
        confidence=0.8,
    ))
    db.commit()
    session_id = session.id
    db.close()
    return session_id


def test_full_package_contains_traceable_observations() -> None:
    session_id = _persist_terminal_session(AssessmentSessionStatus.COMPLETED)
    db = SessionLocal()
    package = build_evidence_package(db, session_id)
    db.close()
    assert package["completion"] == "FULL"
    assert package["model_version_id"]
    assert all(item["turn_ids"] for item in package["competencies"])
    assert all(obs["turn_id"] for item in package["competencies"] for obs in item["observations"])
    assert "score" not in package and "radar" not in package and "profile" not in package


def test_partial_package_marks_unfinished_items() -> None:
    session_id = _persist_terminal_session(AssessmentSessionStatus.PARTIALLY_FINISHED)
    db = SessionLocal()
    package = build_evidence_package(db, session_id)
    db.close()
    assert package["completion"] == "PARTIAL"
    assert any(item["status"] == "INCOMPLETE" for item in package["competencies"])


def test_evidence_package_unknown_session_is_not_found() -> None:
    with TestClient(app) as client:
        response = client.get("/api/assessments/does-not-exist/evidence-package")
    assert response.status_code == 404
