from ..models import AssessmentReport


def answer_report_question(report: AssessmentReport, question: str) -> tuple[str, list[str]]:
    """Deterministic, read-only fallback grounded in the saved report facts."""
    scored = [item for item in report.evaluations if item.score is not None]
    incomplete = [item for item in report.evaluations if item.score is None]
    evidence_ids = sorted({evidence_id for item in report.evaluations for evidence_id in (item.evidence_ids or [])})
    normalized = question.strip()
    if any(word in normalized for word in ("改进", "提升", "建议", "怎么做")):
        if incomplete:
            names = "、".join(item.competency_id for item in incomplete)
            answer = f"建议先为 {names} 补充具体经历、个人行动和结果证据；这些能力当前不可完全评价，不能按 0 分解释。"
        elif scored:
            weakest = min(scored, key=lambda item: item.score or 0)
            answer = f"可优先改善 {weakest.competency_id}：当前为 {weakest.score}/10。建议补充复杂场景、权衡过程和可验证结果。"
        else:
            answer = "当前没有足够的已评分能力，建议先补充测评证据。"
    elif any(word in normalized for word in ("为什么", "分数", "评分", "匹配度")):
        answer = f"当前综合匹配度为 {report.match_score if report.match_score is not None else '待评价'}。该结果只聚合已评价能力；已评价权重为 {round(report.evaluated_weight * 100)}%，未评价能力不会按 0 分处理。"
    else:
        summary = "；".join(f"{item.competency_id}：{item.score}/10" for item in scored) or "暂无已评分能力"
        answer = f"基于报告 v{report.report_version}，能力概况为：{summary}。你可以继续询问某项能力的评分依据或改进建议。"
    return answer, evidence_ids
