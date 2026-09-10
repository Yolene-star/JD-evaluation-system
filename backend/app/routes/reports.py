from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AssessmentReport, AssessmentSession, ReportChatMessage, ReportNarrative, RubricSet
from ..services.evidence_package import build_evidence_package
from ..services.report_service import ReportGenerationError, generate_report
from ..services.rubrics import activate_rubric_set, create_default_rubric_set, get_active_rubric_set
from ..services.report_chat import answer_report_question

router = APIRouter(tags=["reports"])


def _report_payload(report: AssessmentReport) -> dict:
    return {
        "id": report.id,
        "assessment_session_id": report.assessment_session_id,
        "report_version": report.report_version,
        "evidence_package_id": report.evidence_package_id,
        "model_version_id": report.model_version_id,
        "rubric_set_id": report.rubric_set_id,
        "scoring_rule_version": report.scoring_rule_version,
        "completion": report.completion.value,
        "evaluated_weight": report.evaluated_weight,
        "unevaluated_weight": report.unevaluated_weight,
        "match_score": report.match_score,
        "match_score_type": report.match_score_type,
        "status": report.status.value,
        "narrative_status": report.narrative_status.value,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "evaluations": [{"competency_id": item.competency_id, "status": item.status, "score": item.score, "attainment": item.attainment, "level": item.level, "evidence_ids": item.evidence_ids, "matched_indicator_ids": item.matched_indicator_ids, "negative_evidence_ids": item.negative_evidence_ids, "missing_indicator_ids": item.missing_indicator_ids, "confidence": item.confidence, "rationale": item.rationale} for item in report.evaluations],
        "narrative": ({"overview": {"text": report.narrative.overview, "evidenceIds": report.narrative.cited_evidence_ids}, "strengths": report.narrative.strengths, "weaknesses": report.narrative.weaknesses, "recommendations": report.narrative.recommendations} if report.narrative else None),
    }


@router.post("/api/assessment-sessions/{session_id}/reports")
def create_report(session_id: str, payload: dict, db: Session = Depends(get_db)) -> dict:
    session = db.get(AssessmentSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="测评会话不存在")
    if not str(payload.get("idempotency_key", "")).strip():
        raise HTTPException(status_code=422, detail="幂等键不能为空")
    try:
        package = payload.get("evidence_package") or build_evidence_package(db, session_id)
        rubric_id = payload.get("rubric_set_id")
        rubric = db.get(RubricSet, rubric_id) if rubric_id else get_active_rubric_set(db, session.model_version_id)
        if rubric is None and not rubric_id:
            # The stage-three entry point is usable immediately after stage
            # two: create a draft Rubric from the immutable evidence package,
            # then activate it. This does not mutate the confirmed model.
            items = package.get("competencies", [])
            weight = 1.0 / len(items) if items else 0.0
            rubric = create_default_rubric_set(db, session.model_version_id, [{"id": item.get("competency_id"), "name": item.get("competency_id"), "weight": weight} for item in items], version="auto-r1")
            activate_rubric_set(db, rubric.id)
            db.commit()
        if rubric is None:
            raise ReportGenerationError("RUBRIC_NOT_ACTIVE")
        report = generate_report(db, session_id, str(payload.get("evidence_package_id") or session_id), package, rubric.id, str(payload.get("idempotency_key") or ""))
        return _report_payload(report)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (ReportGenerationError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/api/assessment-sessions/{session_id}/reports")
def list_reports(session_id: str, db: Session = Depends(get_db)) -> list[dict]:
    if db.get(AssessmentSession, session_id) is None:
        raise HTTPException(status_code=404, detail="测评会话不存在")
    rows = db.scalars(select(AssessmentReport).where(AssessmentReport.assessment_session_id == session_id).order_by(AssessmentReport.report_version.desc())).all()
    return [_report_payload(row) for row in rows]


@router.get("/api/reports/{report_id}")
def get_report(report_id: str, db: Session = Depends(get_db)) -> dict:
    report = db.get(AssessmentReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    return _report_payload(report)


@router.post("/api/reports/{report_id}/narrative/retry")
def retry_narrative(report_id: str, db: Session = Depends(get_db)) -> dict:
    report = db.get(AssessmentReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    # Deterministic local fallback keeps the retry path usable without an API
    # key; a provider adapter can replace this narrative later without
    # changing any score or evidence fields.
    report.narrative_status = "READY"
    if report.narrative is None:
        incomplete = sum(item.score is None for item in report.evaluations)
        db.add(ReportNarrative(report_id=report.id, overview=("部分能力尚未完成测评，暂不可完全评价。" if incomplete else "报告已根据测评证据生成。"), strengths=[], weaknesses=[], recommendations=[], cited_evidence_ids=[]))
    db.commit()
    return _report_payload(report)


@router.get("/api/reports/{report_id}/scoring-policy")
def scoring_policy(report_id: str, db: Session = Depends(get_db)) -> dict:
    report = db.get(AssessmentReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    return {"scoring_rule_version": report.scoring_rule_version, "attainment_formula": "score / 10", "partial_weight_policy": "evaluated weights are re-normalized", "incomplete_policy": "INCOMPLETE is not scored and is not treated as zero"}


def _chat_payload(item: ReportChatMessage) -> dict:
    return {"id": item.id, "report_id": item.report_id, "role": item.role, "content": item.content, "cited_evidence_ids": item.cited_evidence_ids, "created_at": item.created_at.isoformat() if item.created_at else None}


@router.get("/api/reports/{report_id}/chat/messages")
def report_chat_history(report_id: str, db: Session = Depends(get_db)) -> list[dict]:
    if db.get(AssessmentReport, report_id) is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    rows = db.scalars(select(ReportChatMessage).where(ReportChatMessage.report_id == report_id).order_by(ReportChatMessage.created_at, ReportChatMessage.id)).all()
    return [_chat_payload(item) for item in rows]


@router.post("/api/reports/{report_id}/chat/messages")
def ask_report_agent(report_id: str, payload: dict, db: Session = Depends(get_db)) -> dict:
    report = db.get(AssessmentReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    question = str(payload.get("content", "")).strip()
    if not question:
        raise HTTPException(status_code=422, detail="问题不能为空")
    user_message = ReportChatMessage(report_id=report.id, role="user", content=question, cited_evidence_ids=[])
    db.add(user_message)
    answer, evidence_ids = answer_report_question(report, question)
    agent_message = ReportChatMessage(report_id=report.id, role="agent", content=answer, cited_evidence_ids=evidence_ids)
    db.add(agent_message)
    db.commit()
    return {"reply": answer, "message": _chat_payload(agent_message)}
