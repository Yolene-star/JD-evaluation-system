from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from ..models import (
    AssessmentCompletion,
    AssessmentSession,
    AssessmentSessionStatus,
    CompetencyAssessment,
    CompetencyAssessmentEvidenceSufficiency,
    CompetencyAssessmentStatus,
)
from .assessment_contracts import ConfirmedModelSnapshot

if TYPE_CHECKING:
    from .assessment_ai import AnalysisResult


TERMINAL_COMPETENCY_STATUSES = frozenset(
    {CompetencyAssessmentStatus.SUFFICIENT, CompetencyAssessmentStatus.EXHAUSTED}
)


class InvalidAssessmentTransition(RuntimeError):
    """Raised when a deterministic assessment transition is not allowed."""


@dataclass(frozen=True)
class StateTransition:
    previous_status: AssessmentSessionStatus
    current_status: AssessmentSessionStatus
    next_action: str
    competency_id: str | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_db(instance: AssessmentSession | CompetencyAssessment) -> Session:
    db = object_session(instance)
    if db is None:
        raise InvalidAssessmentTransition("assessment record must be attached to a database session")
    return db


def _session_items(db: Session, assessment_session: AssessmentSession) -> list[CompetencyAssessment]:
    return list(
        db.scalars(
            select(CompetencyAssessment)
            .where(CompetencyAssessment.session_id == assessment_session.id)
            .order_by(CompetencyAssessment.created_at, CompetencyAssessment.id)
        )
    )


def _transition(
    assessment_session: AssessmentSession,
    previous_status: AssessmentSessionStatus,
    next_action: str,
    competency_id: str | None = None,
) -> StateTransition:
    return StateTransition(previous_status, assessment_session.status, next_action, competency_id)


def start_session(
    db: Session,
    assessment_session: AssessmentSession,
    snapshot: ConfirmedModelSnapshot,
) -> StateTransition:
    if assessment_session.status is not AssessmentSessionStatus.READY:
        raise InvalidAssessmentTransition("only READY sessions can start")
    if assessment_session.model_version_id != snapshot.model_version_id:
        raise InvalidAssessmentTransition("snapshot does not belong to this assessment session")
    if not snapshot.competencies:
        raise InvalidAssessmentTransition("a session requires at least one confirmed competency")

    existing_items = _session_items(db, assessment_session)
    if existing_items:
        raise InvalidAssessmentTransition("READY session already has competency assessments")

    now = _now()
    items = [
        CompetencyAssessment(
            session_id=assessment_session.id,
            competency_id=competency.id,
            status=(
                CompetencyAssessmentStatus.ASKING
                if index == 0
                else CompetencyAssessmentStatus.PENDING
            ),
            started_at=now if index == 0 else None,
        )
        for index, competency in enumerate(snapshot.competencies)
    ]
    db.add_all(items)
    db.flush()

    previous_status = assessment_session.status
    assessment_session.status = AssessmentSessionStatus.IN_PROGRESS
    assessment_session.started_at = now
    assessment_session.current_competency_id = items[0].competency_id
    return _transition(assessment_session, previous_status, "ASK_MAIN_QUESTION", items[0].competency_id)


def select_question_scope(
    snapshot: ConfirmedModelSnapshot,
    pending_competencies: list[CompetencyAssessment | str],
) -> list[str]:
    """Return the stable first group of one to three non-terminal competencies."""
    pending_ids: set[str] = set()
    for competency in pending_competencies:
        if isinstance(competency, str):
            pending_ids.add(competency)
        elif competency.status not in TERMINAL_COMPETENCY_STATUSES and competency.status is not CompetencyAssessmentStatus.INCOMPLETE:
            pending_ids.add(competency.competency_id)
    return [item.id for item in snapshot.competencies if item.id in pending_ids][:3]


def pause_session(assessment_session: AssessmentSession) -> StateTransition:
    if assessment_session.status is not AssessmentSessionStatus.IN_PROGRESS:
        raise InvalidAssessmentTransition("only IN_PROGRESS sessions can pause")
    previous_status = assessment_session.status
    assessment_session.status = AssessmentSessionStatus.PAUSED
    assessment_session.paused_at = _now()
    return _transition(assessment_session, previous_status, "PAUSED", assessment_session.current_competency_id)


def resume_session(assessment_session: AssessmentSession) -> StateTransition:
    if assessment_session.status is not AssessmentSessionStatus.PAUSED:
        raise InvalidAssessmentTransition("only PAUSED sessions can resume")
    previous_status = assessment_session.status
    assessment_session.status = AssessmentSessionStatus.IN_PROGRESS
    return _transition(assessment_session, previous_status, "RESUMED", assessment_session.current_competency_id)


def finish_session(assessment_session: AssessmentSession, reason: str) -> StateTransition:
    if assessment_session.status not in {
        AssessmentSessionStatus.IN_PROGRESS,
        AssessmentSessionStatus.PAUSED,
    }:
        raise InvalidAssessmentTransition("only active or paused sessions can finish")
    if not reason.strip():
        raise ValueError("finish reason is required")

    db = _require_db(assessment_session)
    for item in _session_items(db, assessment_session):
        if item.status not in TERMINAL_COMPETENCY_STATUSES:
            item.status = CompetencyAssessmentStatus.INCOMPLETE
            item.completed_at = _now()
    previous_status = assessment_session.status
    assessment_session.status = AssessmentSessionStatus.PARTIALLY_FINISHED
    assessment_session.completion = AssessmentCompletion.PARTIAL
    assessment_session.current_competency_id = None
    assessment_session.completed_at = _now()
    return _transition(assessment_session, previous_status, "PARTIALLY_FINISHED")


def _evidence_sufficiency(analysis: AnalysisResult) -> str:
    value = getattr(analysis, "evidence_sufficiency", None)
    return getattr(value, "value", value)


def _advance_or_complete(
    assessment_session: AssessmentSession,
    db: Session,
) -> StateTransition:
    remaining = [item for item in _session_items(db, assessment_session) if item.status not in TERMINAL_COMPETENCY_STATUSES]
    if not remaining:
        previous_status = assessment_session.status
        assessment_session.status = AssessmentSessionStatus.COMPLETED
        assessment_session.completion = AssessmentCompletion.FULL
        assessment_session.current_competency_id = None
        assessment_session.completed_at = _now()
        return _transition(assessment_session, previous_status, "COMPLETE")

    next_item = next(
        (item for item in remaining if item.status is CompetencyAssessmentStatus.PENDING),
        remaining[0],
    )
    if next_item.status is CompetencyAssessmentStatus.PENDING:
        next_item.status = CompetencyAssessmentStatus.ASKING
        next_item.started_at = _now()
    assessment_session.current_competency_id = next_item.competency_id
    return _transition(assessment_session, assessment_session.status, "ASK_MAIN_QUESTION", next_item.competency_id)


def apply_analysis(
    assessment_session: AssessmentSession,
    competency_assessment: CompetencyAssessment,
    analysis: AnalysisResult,
) -> StateTransition:
    if assessment_session.status is not AssessmentSessionStatus.IN_PROGRESS:
        raise InvalidAssessmentTransition("analysis can only apply to an IN_PROGRESS session")
    if competency_assessment.session_id != assessment_session.id:
        raise InvalidAssessmentTransition("competency assessment does not belong to this session")
    if competency_assessment.status in TERMINAL_COMPETENCY_STATUSES | {CompetencyAssessmentStatus.INCOMPLETE}:
        raise InvalidAssessmentTransition("analysis cannot be applied to a terminal competency")

    db = _require_db(competency_assessment)
    sufficiency = _evidence_sufficiency(analysis)
    if sufficiency == CompetencyAssessmentEvidenceSufficiency.SUFFICIENT.value:
        competency_assessment.status = CompetencyAssessmentStatus.SUFFICIENT
        competency_assessment.evidence_sufficiency = CompetencyAssessmentEvidenceSufficiency.SUFFICIENT
        competency_assessment.completed_at = _now()
        return _advance_or_complete(assessment_session, db)

    competency_assessment.evidence_sufficiency = (
        CompetencyAssessmentEvidenceSufficiency.UNCERTAIN
        if sufficiency == CompetencyAssessmentEvidenceSufficiency.UNCERTAIN.value
        else CompetencyAssessmentEvidenceSufficiency.INSUFFICIENT
    )
    profile = getattr(assessment_session, "assessment_profile", None) or {}
    depth = profile.get("assessment_depth", "STANDARD")
    max_follow_ups = {"QUICK": 0, "STANDARD": 2, "DEEP": 3}.get(str(depth).upper(), 2)
    if competency_assessment.follow_up_count < max_follow_ups:
        competency_assessment.follow_up_count += 1
        competency_assessment.status = CompetencyAssessmentStatus.FOLLOW_UP
        assessment_session.current_competency_id = competency_assessment.competency_id
        return _transition(
            assessment_session,
            assessment_session.status,
            "ASK_FOLLOW_UP",
            competency_assessment.competency_id,
        )

    competency_assessment.status = CompetencyAssessmentStatus.EXHAUSTED
    competency_assessment.completed_at = _now()
    return _advance_or_complete(assessment_session, db)
