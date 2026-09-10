import json
from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from ..models import AssessmentEvent


ASSESSMENT_EVENT_ACTIONS = frozenset(
    {
        "ASSESSMENT_CREATED",
        "ASSESSMENT_STARTED",
        "ANSWER_SUBMITTED",
        "ANSWER_ANALYZED",
        "EVIDENCE_RECORDED",
        "FOLLOW_UP_GENERATED",
        "COMPETENCY_SUFFICIENT",
        "COMPETENCY_EXHAUSTED",
        "ASSESSMENT_PAUSED",
        "ASSESSMENT_RESUMED",
        "ASSESSMENT_COMPLETED",
        "ASSESSMENT_PARTIALLY_FINISHED",
        "AI_RETRY_REQUESTED",
        "AI_INVALID_RESPONSE",
    }
)


def record_event(
    db: Session,
    session_id: str,
    action: str,
    payload: Mapping[str, Any] | None = None,
) -> AssessmentEvent:
    """Append an event to the caller-owned transaction without committing it."""
    if action not in ASSESSMENT_EVENT_ACTIONS:
        raise ValueError(f"unsupported assessment event action: {action}")
    event = AssessmentEvent(
        session_id=session_id,
        action=action,
        payload=json.dumps(dict(payload or {}), ensure_ascii=False),
    )
    db.add(event)
    return event
