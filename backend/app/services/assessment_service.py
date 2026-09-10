from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agent.interview_agent import AgentProcessingError, InterviewAgent
from ..agent.schemas import AgentStatus
from ..agent.tools import EvidenceTool
from ..models import AssessmentEvent, AssessmentSession, AssessmentSessionStatus, AssessmentTurn, AssessmentTurnRole, AssessmentTurnType, CompetencyAssessment, CompetencyAssessmentStatus, EvidenceObservation
from .assessment_ai import GeneratedQuestion, InvalidAIResponse, RetryableAIError, analyze_answer, generate_main_question
from .assessment_contracts import ConfirmedModelSnapshot, get_confirmed_model_snapshot
from .assessment_events import record_event
from .assessment_state import InvalidAssessmentTransition, finish_session, pause_session, resume_session, start_session
from .resume_context import freeze_resume_snapshot, get_current_resume_context, serialize_resume_snapshot


class AssessmentServiceError(ValueError):
    def __init__(self, code: str, message: str | None = None):
        self.code = code
        super().__init__(message or code)


def _items(db: Session, session: AssessmentSession) -> list[CompetencyAssessment]:
    return list(db.scalars(select(CompetencyAssessment).where(CompetencyAssessment.session_id == session.id).order_by(CompetencyAssessment.created_at, CompetencyAssessment.id)))


def _snapshot(session: AssessmentSession, db: Session) -> ConfirmedModelSnapshot:
    return get_confirmed_model_snapshot(db, session.project_id, session.model_version_id)


def _turn_index(db: Session, session: AssessmentSession) -> int:
    return (db.scalar(select(AssessmentTurn.turn_index).where(AssessmentTurn.session_id == session.id).order_by(AssessmentTurn.turn_index.desc())) or 0) + 1


def _latest_question(db: Session, session: AssessmentSession) -> AssessmentTurn | None:
    return db.scalars(select(AssessmentTurn).where(AssessmentTurn.session_id == session.id, AssessmentTurn.role == AssessmentTurnRole.SYSTEM, AssessmentTurn.turn_type.in_([AssessmentTurnType.MAIN_QUESTION, AssessmentTurnType.FOLLOW_UP])).order_by(AssessmentTurn.turn_index.desc(), AssessmentTurn.created_at.desc())).first()


def _question_payload(turn: AssessmentTurn | None) -> dict | None:
    if turn is None:
        return None
    return {"id": turn.id, "content": turn.content, "turn_type": turn.turn_type, "covered_competency_ids": turn.covered_competency_ids, "follow_up_target_competency_id": turn.covered_competency_ids[0] if turn.turn_type == AssessmentTurnType.FOLLOW_UP else None, "background_reference": None}


def _make_question(session: AssessmentSession, db: Session, target_ids: list[str], follow_up_target: str | None = None) -> dict:
    if not 1 <= len(target_ids) <= 3 or len(set(target_ids)) != len(target_ids):
        raise AssessmentServiceError("INVALID_QUESTION_SCOPE")
    snapshot = _snapshot(session, db)
    competencies = [next((item for item in snapshot.competencies if item.id == item_id), None) for item_id in target_ids]
    if any(item is None for item in competencies):
        raise AssessmentServiceError("COMPETENCY_NOT_IN_SNAPSHOT")
    try:
        if follow_up_target:
            raise RetryableAIError("follow-up uses targeted prompt")
        question = generate_main_question(snapshot, competencies, [], [], transport=None)
    except RetryableAIError:
        prefix = "补充说明" if follow_up_target else "请描述一次与你目标岗位相关的实际项目经历"
        question = GeneratedQuestion(content=f"{prefix}，重点说明你在{competencies[0].name}中的具体做法、依据和结果。", covered_competency_ids=target_ids, turn_type="FOLLOW_UP" if follow_up_target else "MAIN_QUESTION")
    except InvalidAIResponse as exc:
        raise AssessmentServiceError("AI_INVALID_RESPONSE", str(exc)) from exc
    turn = AssessmentTurn(session_id=session.id, competency_assessment_id=next(item.id for item in _items(db, session) if item.competency_id == target_ids[0]), turn_index=_turn_index(db, session), role=AssessmentTurnRole.SYSTEM, turn_type=AssessmentTurnType.FOLLOW_UP if follow_up_target else AssessmentTurnType.MAIN_QUESTION, content=question.content, covered_competency_ids=list(target_ids))
    db.add(turn)
    db.flush()
    if follow_up_target:
        record_event(db, session.id, "FOLLOW_UP_GENERATED", {"competency_id": follow_up_target, "turn_id": turn.id})
    return _question_payload(turn) or {}


def create_session(
    db: Session,
    project_id: str,
    model_version_id: str | None = None,
    *,
    use_resume_context: bool = False,
) -> AssessmentSession:
    snapshot = get_confirmed_model_snapshot(db, project_id, model_version_id)
    session = AssessmentSession(project_id=project_id, model_version_id=snapshot.model_version_id)
    db.add(session)
    db.flush()
    if use_resume_context:
        freeze_resume_snapshot(db, session, get_current_resume_context(db, project_id))
    record_event(db, session.id, "ASSESSMENT_CREATED", {"model_version_id": snapshot.model_version_id})
    db.commit()
    db.refresh(session)
    return session


def _latest_agent_status(db: Session, session_id: str) -> dict | None:
    event = db.scalars(
        select(AssessmentEvent)
        .where(
            AssessmentEvent.session_id == session_id,
            AssessmentEvent.action == "AGENT_DECISION_RECORDED",
        )
        .order_by(AssessmentEvent.created_at.desc(), AssessmentEvent.id.desc())
    ).first()
    if event is None:
        return None
    return json.loads(event.payload).get("agent_status")


def serialize_session(
    db: Session,
    session: AssessmentSession,
    current_question: dict | None = None,
    retryable: bool = False,
    error: str | None = None,
    agent_status: AgentStatus | dict | None = None,
) -> dict:
    items = _items(db, session)
    snapshot = _snapshot(session, db)
    item_by_id = {item.competency_id: item for item in items}
    turns = list(db.scalars(select(AssessmentTurn).where(AssessmentTurn.session_id == session.id).order_by(AssessmentTurn.turn_index, AssessmentTurn.created_at, AssessmentTurn.id)))
    if current_question is None:
        current_question = _question_payload(_latest_question(db, session))
    competencies = [{"competency_id": competency.id, "name": competency.name, "status": item_by_id[competency.id].status if competency.id in item_by_id else CompetencyAssessmentStatus.PENDING, "follow_up_count": item_by_id[competency.id].follow_up_count if competency.id in item_by_id else 0, "evidence_sufficiency": item_by_id[competency.id].evidence_sufficiency if competency.id in item_by_id else "UNCERTAIN"} for competency in snapshot.competencies]
    competency_names = {item["competency_id"]: item["name"] for item in competencies}
    observations = list(db.scalars(select(EvidenceObservation).where(EvidenceObservation.session_id == session.id).order_by(EvidenceObservation.created_at, EvidenceObservation.id)))
    evidence_groups = []
    for competency_id in dict.fromkeys(item.competency_id for item in observations):
        assessment = item_by_id.get(competency_id)
        grouped = [item for item in observations if item.competency_id == competency_id]
        evidence_groups.append({
            "competency_id": competency_id,
            "competency_name": competency_names.get(competency_id, competency_id),
            "sufficiency": getattr(assessment.evidence_sufficiency, "value", assessment.evidence_sufficiency) if assessment else "UNCERTAIN",
            "observations": [item.source_excerpt or item.excerpt for item in grouped if item.source_excerpt or item.excerpt],
        })
    completed = sum(item["status"] in {CompetencyAssessmentStatus.SUFFICIENT, CompetencyAssessmentStatus.EXHAUSTED} for item in competencies)
    if agent_status is None:
        agent_status = _latest_agent_status(db, session.id)
    return {
        "id": session.id,
        "session_id": session.id,
        "project_id": session.project_id,
        "model_version_id": session.model_version_id,
        "status": session.status,
        "completion": session.completion,
        "current_competency_id": session.current_competency_id,
        "current_question": current_question,
        "competencies": competencies,
        "turns": [
            {
                "id": turn.id,
                "role": turn.role,
                "turn_type": turn.turn_type,
                "content": turn.content,
                "covered_competency_ids": turn.covered_competency_ids,
                "turn_index": turn.turn_index,
            }
            for turn in turns
        ],
        "progress": {"completed": completed, "total": len(competencies)},
        "retryable": retryable,
        "error": error,
        "agent_status": agent_status.model_dump(mode="json") if isinstance(agent_status, AgentStatus) else agent_status,
        "evidence_groups": evidence_groups,
        "resume_context": serialize_resume_snapshot(db, session.id),
    }


def start_assessment(db: Session, session: AssessmentSession) -> dict:
    try:
        transition = start_session(db, session, _snapshot(session, db))
        record_event(db, session.id, "ASSESSMENT_STARTED", {"competency_id": transition.competency_id})
        question = _make_question(session, db, [transition.competency_id])
        db.commit()
    except (InvalidAssessmentTransition, AssessmentServiceError):
        db.rollback()
        raise
    return serialize_session(db, session, question)


def _find_retry(db: Session, session: AssessmentSession) -> tuple[AssessmentTurn, str] | None:
    events = db.scalars(select(AssessmentEvent).where(AssessmentEvent.session_id == session.id, AssessmentEvent.action == "AI_RETRY_REQUESTED").order_by(AssessmentEvent.created_at.desc(), AssessmentEvent.id.desc())).all()
    for event in events:
        payload = json.loads(event.payload)
        answer = db.get(AssessmentTurn, payload.get("turn_id"))
        if answer and answer.session_id == session.id and answer.role is AssessmentTurnRole.USER:
            analyzed = any(
                json.loads(row.payload).get("turn_id") == answer.id
                for row in db.scalars(
                    select(AssessmentEvent).where(
                        AssessmentEvent.session_id == session.id,
                        AssessmentEvent.action == "ANSWER_ANALYZED",
                    )
                )
            )
            if analyzed:
                continue
            return answer, str(payload.get("error", "AI 调用失败"))
    return None


def _process_answer(db: Session, session: AssessmentSession, answer: AssessmentTurn, *, retry: bool = False) -> dict:
    try:
        result = InterviewAgent(
            db,
            evidence_tool=EvidenceTool(analyze_fn=analyze_answer),
        ).process_turn(session, answer, retry=retry)
    except AgentProcessingError as exc:
        raise AssessmentServiceError(exc.code, str(exc)) from exc
    if result.retryable:
        db.commit()
        return serialize_session(db, session, retryable=True, error=result.error, agent_status=result.agent_status)
    db.commit()
    return serialize_session(db, session, result.current_question, agent_status=result.agent_status)


def submit_turn(db: Session, session: AssessmentSession, content: str, idempotency_key: str) -> dict:
    existing = db.scalar(select(AssessmentTurn).where(AssessmentTurn.session_id == session.id, AssessmentTurn.idempotency_key == idempotency_key))
    if existing:
        retry = _find_retry(db, session)
        return serialize_session(db, session, retryable=bool(retry), error=retry[1] if retry else None)
    if session.status is not AssessmentSessionStatus.IN_PROGRESS:
        raise AssessmentServiceError("ASSESSMENT_NOT_ACTIVE")
    question = _latest_question(db, session)
    if question is None:
        raise AssessmentServiceError("QUESTION_NOT_FOUND")
    covered = list(question.covered_competency_ids or [])
    items_by_id = {item.competency_id: item for item in _items(db, session)}
    if any(item_id not in items_by_id for item_id in covered):
        raise AssessmentServiceError("COMPETENCY_SESSION_MISMATCH")
    answer = AssessmentTurn(session_id=session.id, competency_assessment_id=items_by_id[covered[0]].id, turn_index=_turn_index(db, session), role=AssessmentTurnRole.USER, turn_type=AssessmentTurnType.ANSWER, content=content, covered_competency_ids=covered, idempotency_key=idempotency_key)
    db.add(answer)
    db.flush()
    record_event(db, session.id, "ANSWER_SUBMITTED", {"turn_id": answer.id})
    try:
        return _process_answer(db, session, answer)
    except AssessmentServiceError:
        record_event(db, session.id, "AI_INVALID_RESPONSE", {"turn_id": answer.id})
        db.commit()
        raise


def retry_turn(db: Session, session: AssessmentSession) -> dict:
    if session.status is not AssessmentSessionStatus.IN_PROGRESS:
        raise AssessmentServiceError("ASSESSMENT_NOT_ACTIVE")
    retry = _find_retry(db, session)
    if retry is None:
        raise AssessmentServiceError("NO_RETRY_AVAILABLE")
    return _process_answer(db, session, retry[0], retry=True)


def transition_session(db: Session, session: AssessmentSession, action: str, reason: str | None = None) -> dict:
    try:
        if action == "pause":
            pause_session(session)
            record_event(db, session.id, "ASSESSMENT_PAUSED", {})
        elif action == "resume":
            resume_session(session)
            record_event(db, session.id, "ASSESSMENT_RESUMED", {})
        elif action == "finish":
            finish_session(session, reason or "用户结束测评")
            record_event(db, session.id, "ASSESSMENT_PARTIALLY_FINISHED", {"reason": reason or ""})
        else:
            raise AssessmentServiceError("UNKNOWN_TRANSITION")
    except InvalidAssessmentTransition as exc:
        raise AssessmentServiceError("INVALID_ASSESSMENT_TRANSITION", str(exc)) from exc
    db.commit()
    return serialize_session(db, session)
