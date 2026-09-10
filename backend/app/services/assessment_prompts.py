from typing import Any


def build_question_prompt(competencies: list[Any], jd_evidence: list[Any], transcript: list[Any]) -> str:
    names = "、".join(str(item.name) for item in competencies)
    return f"只生成一个关于以下能力的文字测评主问题：{names}。必须依据随请求提供的 JD 证据，只能覆盖输入的能力项，不得创建能力项、修改权重或给出分数。输出 JSON：content、covered_competency_ids、turn_type；turn_type 必须是 MAIN_QUESTION。"


def build_analysis_prompt(competency: Any, jd_evidence: list[Any], transcript: list[Any]) -> str:
    return f"只分析能力项“{competency.name}”，并结合随请求提供的该能力 JD 证据和本能力对话记录输出结构化 JSON。只能引用当前能力项；evidence 的 excerpt 必须来自用户回答；不要计算正式分数。字段：answer_summary、evidence、evidence_sufficiency、needs_follow_up、follow_up_reason、follow_up_question。"
