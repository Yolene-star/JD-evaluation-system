from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AssessmentEvent, AssessmentSession, AssessmentSessionStatus, Project
from ..services.assessment_service import AssessmentServiceError, create_session, retry_turn, serialize_session, start_assessment, submit_turn, transition_session

router = APIRouter(tags=["assessments"])


def get_session(session_id: str, db: Session) -> AssessmentSession:
    session = db.get(AssessmentSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="测评会话不存在")
    return session


@router.post("/api/projects/{project_id}/assessments")
def create(project_id: str, payload: dict | None = None, db: Session = Depends(get_db)) -> dict:
    if not db.get(Project, project_id):
        raise HTTPException(status_code=404, detail="项目不存在")
    try:
        return serialize_session(db, create_session(db, project_id, (payload or {}).get("model_version_id")))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/api/assessments/{session_id}")
def get(session_id: str, db: Session = Depends(get_db)) -> dict:
    return serialize_session(db, get_session(session_id, db))


@router.post("/api/assessments/{session_id}/start")
def start(session_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        return start_assessment(db, get_session(session_id, db))
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/api/assessments/{session_id}/turns")
def turn(session_id: str, payload: dict, db: Session = Depends(get_db)) -> dict:
    content = str(payload.get("content", "")).strip()
    key = str(payload.get("idempotency_key", "")).strip()
    if not content or not key:
        raise HTTPException(status_code=422, detail="回答和幂等键不能为空")
    try:
        return submit_turn(db, get_session(session_id, db), content, key)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/api/assessments/{session_id}/pause")
def pause(session_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        return transition_session(db, get_session(session_id, db), "pause")
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/api/assessments/{session_id}/resume")
def resume(session_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        return transition_session(db, get_session(session_id, db), "resume")
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/api/assessments/{session_id}/finish")
def finish(session_id: str, payload: dict, db: Session = Depends(get_db)) -> dict:
    if not payload.get("confirm"):
        raise HTTPException(status_code=422, detail="结束测评需要确认")
    try:
        return transition_session(db, get_session(session_id, db), "finish", str(payload.get("reason", "用户结束测评")))
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/api/assessments/{session_id}/retry")
def retry(session_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        return retry_turn(db, get_session(session_id, db))
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/api/assessments/{session_id}/events")
def events(session_id: str, db: Session = Depends(get_db)) -> list[dict]:
    get_session(session_id, db)
    rows = db.scalars(select(AssessmentEvent).where(AssessmentEvent.session_id == session_id).order_by(AssessmentEvent.created_at, AssessmentEvent.id)).all()
    return [{"id": row.id, "action": row.action, "payload": row.payload, "created_at": row.created_at.isoformat()} for row in rows]
