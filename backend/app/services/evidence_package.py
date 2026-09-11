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
    grouped: dict[str, dict] = {}
    status_rank = {
        "PENDING": 0,
        "ASKING": 1,
        "FOLLOW_UP": 2,
        "INCOMPLETE": 3,
        "EXHAUSTED": 4,
        "SUFFICIENT": 5,
    }
    sufficiency_rank = {"UNCERTAIN": 0, "INSUFFICIENT": 1, "SUFFICIENT": 2}
    for item in assessments:
        observations = list(db.scalars(select(EvidenceObservation).where(EvidenceObservation.competency_assessment_id == item.id).order_by(EvidenceObservation.created_at, EvidenceObservation.id)))
        competency_id = item.competency_id
        current = grouped.setdefault(
            competency_id,
            {
                "competency_id": competency_id,
                "status": item.status,
                "evidence_sufficiency": item.evidence_sufficiency,
                "turn_ids": set(),
                "observations": {},
                "matched_indicators": [],
                "missing_indicators": [],
            },
        )
        if status_rank.get(getattr(item.status, "value", item.status), 0) > status_rank.get(getattr(current["status"], "value", current["status"]), 0):
            current["status"] = item.status
        if sufficiency_rank.get(getattr(item.evidence_sufficiency, "value", item.evidence_sufficiency), 0) > sufficiency_rank.get(getattr(current["evidence_sufficiency"], "value", current["evidence_sufficiency"]), 0):
            current["evidence_sufficiency"] = item.evidence_sufficiency
        for observation in observations:
            current["turn_ids"].add(observation.turn_id)
            current["observations"][observation.id] = {
                "id": observation.id,
                "turn_id": observation.turn_id,
                "type": observation.evidence_type,
                "excerpt": observation.excerpt,
                "summary": observation.summary,
                "source_excerpt": observation.source_excerpt,
                "confidence": observation.confidence,
            }
    result = [
        {
            "competency_id": item["competency_id"],
            "status": item["status"],
            "evidence_sufficiency": item["evidence_sufficiency"],
            "turn_ids": sorted(item["turn_ids"]),
            "observations": list(item["observations"].values()),
            "matched_indicators": list(item["matched_indicators"]),
            "missing_indicators": list(item["missing_indicators"]),
        }
        for item in grouped.values()
    ]
    return {"session_id": session.id, "model_version_id": session.model_version_id, "completion": "FULL" if session.status is AssessmentSessionStatus.COMPLETED else "PARTIAL", "competencies": result}
