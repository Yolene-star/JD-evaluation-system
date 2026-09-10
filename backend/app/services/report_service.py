from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    AssessmentReport,
    AssessmentReportCompletion,
    AssessmentReportStatus,
    AssessmentSession,
    AssessmentSessionStatus,
    CompetencyEvaluation,
    ModelVersion,
    ReportNarrative,
    ReportNarrativeStatus,
    RubricSet,
    RubricSetStatus,
)
from .profile import NarrativeValidationError, generate_profile_narrative
from .scoring import score_evidence_package


class ReportGenerationError(ValueError):
    pass


def _enum_value(value):
    return getattr(value, "value", value)


def _rubric_facts(rubric: RubricSet) -> dict[str, dict]:
    return {
        item.competency_id: {
            "competency_id": item.competency_id,
            "indicators": list(item.indicators or []),
            "weight": float((item.scoring_rules or {}).get("weight", 0.0)),
        }
        for item in rubric.competencies
    }


def generate_report(
    db: Session,
    session_id: str,
    evidence_package_id: str,
    evidence_package: dict,
    rubric_set_id: str,
    idempotency_key: str,
    *,
    narrative_adapter=None,
) -> AssessmentReport:
    session = db.get(AssessmentSession, session_id)
    if session is None:
        raise KeyError("assessment session not found")
    if session.status not in {AssessmentSessionStatus.COMPLETED, AssessmentSessionStatus.PARTIALLY_FINISHED}:
        raise ReportGenerationError("EVIDENCE_PACKAGE_NOT_TERMINAL")
    existing = db.scalar(select(AssessmentReport).where(AssessmentReport.assessment_session_id == session_id, AssessmentReport.idempotency_key == idempotency_key))
    if existing is not None:
        return existing
    rubric = db.get(RubricSet, rubric_set_id)
    if rubric is None:
        raise KeyError("rubric set not found")
    if rubric.status is not RubricSetStatus.ACTIVE:
        raise ReportGenerationError("RUBRIC_NOT_ACTIVE")
    if rubric.model_version_id != session.model_version_id or evidence_package.get("model_version_id") != session.model_version_id:
        raise ReportGenerationError("MODEL_VERSION_MISMATCH")
    rubrics = _rubric_facts(rubric)
    package_items = evidence_package.get("competencies", [])
    invalid_competency = any(str(item.get("competency_id")) not in rubrics for item in package_items)
    known_evidence = {
        str(observation.get("id"))
        for item in package_items
        for observation in (item.get("observations", []) or [])
        if observation.get("id") is not None
    }
    score = score_evidence_package(evidence_package, rubrics)
    latest = db.scalar(select(func.max(AssessmentReport.report_version)).where(AssessmentReport.assessment_session_id == session_id)) or 0
    report = AssessmentReport(
        assessment_session_id=session_id,
        report_version=int(latest) + 1,
        evidence_package_id=evidence_package_id,
        model_version_id=session.model_version_id,
        rubric_set_id=rubric.id,
        scoring_rule_version=rubric.scoring_rule_version,
        completion=AssessmentReportCompletion(_enum_value(evidence_package.get("completion", "PARTIAL"))),
        evaluated_weight=score.evaluated_weight,
        unevaluated_weight=score.unevaluated_weight,
        match_score=score.match_score,
        match_score_type=score.match_score_type,
        status=AssessmentReportStatus.READY,
        narrative_status=ReportNarrativeStatus.PENDING_RETRY,
        idempotency_key=idempotency_key,
    )
    db.add(report)
    db.flush()
    for evaluation in score.evaluations:
        db.add(CompetencyEvaluation(report_id=report.id, competency_id=evaluation.competency_id, status=evaluation.status, score=evaluation.score, attainment=evaluation.attainment, level=evaluation.level, evidence_ids=evaluation.evidence_ids, matched_indicator_ids=evaluation.matched_indicator_ids, negative_evidence_ids=evaluation.negative_evidence_ids, missing_indicator_ids=evaluation.missing_indicator_ids, confidence=evaluation.confidence, rationale=evaluation.rationale))
    facts = {"report_id": report.id, "match_score": report.match_score, "match_score_type": report.match_score_type, "evaluations": [evaluation.__dict__ for evaluation in score.evaluations], "evidence_ids": sorted(known_evidence)}
    if narrative_adapter is not None and not invalid_competency:
        try:
            narrative = generate_profile_narrative(facts, narrative_adapter)
            report.narrative_status = ReportNarrativeStatus.READY
            db.add(ReportNarrative(report_id=report.id, overview=narrative["overview"], strengths=narrative["strengths"], weaknesses=narrative["weaknesses"], recommendations=narrative["recommendations"], cited_evidence_ids=narrative["cited_evidence_ids"]))
        except (NarrativeValidationError, Exception):
            report.narrative_status = ReportNarrativeStatus.PENDING_RETRY
    db.commit()
    db.refresh(report)
    return report
