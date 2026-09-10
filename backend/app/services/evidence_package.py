from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AssessmentSession, AssessmentSessionStatus, AssessmentTurn, CompetencyAssessment, EvidenceObservation


class EvidencePackageNotReady(ValueError):
    pass


def build_evidence_package(db: Session, session_id: str) -> dict:
    session = db.get(AssessmentSession, session_id)
    if not session:
        raise KeyError("assessment session not found")
    if session.status not in {AssessmentSessionStatus.COMPLETED, AssessmentSessionStatus.PARTIALLY_FINISHED}:
        raise EvidencePackageNotReady("测评尚未完成，暂不能导出证据包")
    assessments = list(db.scalars(select(CompetencyAssessment).where(CompetencyAssessment.session_id == session.id).order_by(CompetencyAssessment.created_at, CompetencyAssessment.id)))
    result = []
    for item in assessments:
        observations = list(db.scalars(select(EvidenceObservation).where(EvidenceObservation.competency_assessment_id == item.id).order_by(EvidenceObservation.created_at, EvidenceObservation.id)))
        result.append({"competency_id": item.competency_id, "status": item.status, "evidence_sufficiency": item.evidence_sufficiency, "turn_ids": sorted({observation.turn_id for observation in observations}), "observations": [{"id": observation.id, "turn_id": observation.turn_id, "type": observation.evidence_type, "excerpt": observation.excerpt, "summary": observation.summary, "source_excerpt": observation.source_excerpt, "confidence": observation.confidence} for observation in observations]})
    return {"session_id": session.id, "model_version_id": session.model_version_id, "completion": "FULL" if session.status is AssessmentSessionStatus.COMPLETED else "PARTIAL", "competencies": result}
