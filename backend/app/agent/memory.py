from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    AssessmentSession,
    AssessmentTurn,
    CompetencyAssessment,
    CompetencyAssessmentStatus,
    EvidenceObservation,
)
from ..services.assessment_contracts import (
    ConfirmedModelSnapshot,
    get_confirmed_model_snapshot,
)
from .schemas import (
    CompetencyMemoryItem,
    ConversationMemoryItem,
    EvidenceMemoryItem,
    PlannerContext,
)


SnapshotLoader = Callable[[Session, str, str | None], ConfirmedModelSnapshot]


def _value(value: object) -> str:
    return str(getattr(value, "value", value))


class AssessmentMemory:
    def __init__(
        self,
        db: Session,
        snapshot_loader: SnapshotLoader = get_confirmed_model_snapshot,
    ) -> None:
        self.db = db
        self.snapshot_loader = snapshot_loader

    def get_conversation(self, session_id: str) -> list[ConversationMemoryItem]:
        turns = self.db.scalars(
            select(AssessmentTurn)
            .where(AssessmentTurn.session_id == session_id)
            .order_by(AssessmentTurn.turn_index, AssessmentTurn.created_at, AssessmentTurn.id)
        )
        return [
            ConversationMemoryItem(
                turn_id=turn.id,
                turn_index=turn.turn_index,
                role=_value(turn.role),
                turn_type=_value(turn.turn_type),
                content=turn.content,
                covered_competency_ids=list(turn.covered_competency_ids or []),
            )
            for turn in turns
        ]

    def get_evidence(self, session_id: str) -> list[EvidenceMemoryItem]:
        observations = self.db.scalars(
            select(EvidenceObservation)
            .where(EvidenceObservation.session_id == session_id)
            .order_by(EvidenceObservation.created_at, EvidenceObservation.id)
        )
        return [
            EvidenceMemoryItem(
                evidence_id=observation.id,
                competency_id=observation.competency_id,
                turn_id=observation.turn_id,
                evidence_type=_value(observation.evidence_type),
                summary=observation.summary,
                source_excerpt=observation.source_excerpt or observation.excerpt,
                confidence=observation.confidence,
            )
            for observation in observations
        ]

    def get_competencies(self, session: AssessmentSession) -> list[CompetencyMemoryItem]:
        snapshot = self.snapshot_loader(
            self.db,
            session.project_id,
            session.model_version_id,
        )
        assessments = {
            item.competency_id: item
            for item in self.db.scalars(
                select(CompetencyAssessment).where(
                    CompetencyAssessment.session_id == session.id
                )
            )
        }
        result: list[CompetencyMemoryItem] = []
        for competency in snapshot.competencies:
            assessment = assessments.get(competency.id)
            result.append(
                CompetencyMemoryItem(
                    competency_id=competency.id,
                    name=competency.name,
                    status=_value(
                        assessment.status
                        if assessment is not None
                        else CompetencyAssessmentStatus.PENDING
                    ),
                    follow_up_count=assessment.follow_up_count if assessment is not None else 0,
                    evidence_sufficiency=_value(
                        assessment.evidence_sufficiency
                        if assessment is not None
                        else "UNCERTAIN"
                    ),
                )
            )
        return result

    def get_context(self, session: AssessmentSession) -> PlannerContext:
        competencies = self.get_competencies(session)
        terminal_statuses = {
            CompetencyAssessmentStatus.SUFFICIENT.value,
            CompetencyAssessmentStatus.EXHAUSTED.value,
            CompetencyAssessmentStatus.INCOMPLETE.value,
        }
        return PlannerContext(
            session_id=session.id,
            session_status=_value(session.status),
            current_competency_id=session.current_competency_id,
            competencies=competencies,
            conversation=self.get_conversation(session.id),
            evidence=self.get_evidence(session.id),
            remaining_competency_ids=[
                item.competency_id
                for item in competencies
                if item.status not in terminal_statuses
            ],
        )
