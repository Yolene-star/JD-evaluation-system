import json

from sqlalchemy.orm import Session

from ..models import AuditEvent


def record_event(db: Session, project_id: str, action: str, payload: dict | None = None) -> AuditEvent:
    event = AuditEvent(project_id=project_id, action=action, payload=json.dumps(payload or {}, ensure_ascii=False))
    db.add(event)
    return event
