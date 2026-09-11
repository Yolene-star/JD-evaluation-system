from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AssessmentReport, CompetencyEvaluation, EvidenceObservation, ReportChatMessage
from .assessment_ai import _call_structured


class ReportChatResult(BaseModel):
    answer: str = Field(min_length=1)
    cited_evidence_ids: list[str] = Field(default_factory=list)


REPORT_CHAT_PROMPT = """你是岗位能力评价报告咨询 Agent。请基于提供的报告 JSON、能力评价、可引用证据和历史对话，用自然、具体、克制的中文回答用户问题。
只解释数据库中已有的报告事实，不修改分数、状态、模型或历史记录，不把未评价能力当成 0 分，不补造经历。若证据不足，明确说明还缺什么面试证据。
必须只返回 JSON，格式为：{"answer":"自然语言回答","cited_evidence_ids":["数据库中的证据ID"]}。answer 必须是完整回答，不能只返回关键词。
"""


def _report_context(db: Session, report: AssessmentReport) -> dict:
    evaluations = list(db.scalars(select(CompetencyEvaluation).where(CompetencyEvaluation.report_id == report.id)))
    evidence_ids = sorted({item_id for item in evaluations for item_id in (item.evidence_ids or [])})
    evidence = list(db.scalars(select(EvidenceObservation).where(EvidenceObservation.id.in_(evidence_ids)))) if evidence_ids else []
    return {
        "report": {
            "version": report.report_version,
            "completion": getattr(report.completion, "value", report.completion),
            "evaluated_weight": report.evaluated_weight,
            "unevaluated_weight": report.unevaluated_weight,
            "match_score": report.match_score,
            "match_score_type": report.match_score_type,
            "scoring_rule_version": report.scoring_rule_version,
        },
        "evaluations": [{
            "competency_id": item.competency_id, "status": item.status, "score": item.score,
            "attainment": item.attainment, "level": item.level, "rationale": item.rationale,
            "evidence_ids": item.evidence_ids or [], "missing_indicator_ids": item.missing_indicator_ids or [],
        } for item in evaluations],
        "evidence": [{"id": item.id, "text": item.summary or item.excerpt, "turn_id": item.turn_id} for item in evidence],
    }


def answer_report_question(db: Session, report: AssessmentReport, question: str) -> tuple[str, list[str]]:
    history = list(db.scalars(select(ReportChatMessage).where(ReportChatMessage.report_id == report.id).order_by(ReportChatMessage.created_at, ReportChatMessage.id)))
    payload = {"question": question, "report_context": _report_context(db, report), "conversation": [{"role": item.role, "content": item.content} for item in history[-12:]]}
    result = _call_structured(REPORT_CHAT_PROMPT, payload, ReportChatResult)
    allowed_ids = {item["id"] for item in payload["report_context"]["evidence"]}
    return result.answer.strip(), [item for item in result.cited_evidence_ids if item in allowed_ids]
