from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, is_dataclass
from typing import Any, Callable
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..config import get_llm_api_key, is_llm_analysis_enabled, settings
from ..models import EvidenceType


class InvalidAIResponse(ValueError):
    """Raised when structured model output violates the assessment contract."""


class RetryableAIError(RuntimeError):
    """Raised when the provider cannot produce a usable structured response."""


class EvidenceResult(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    competency_id: str
    type: EvidenceType
    excerpt: str
    summary: str = ""
    confidence: float = Field(ge=0.0, le=1.0)
    validation_note: str | None = None


class AnalysisResult(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    answer_summary: str
    evidence: list[EvidenceResult]
    evidence_sufficiency: str
    needs_follow_up: bool
    follow_up_reason: str = ""
    follow_up_question: str = ""

    @field_validator("evidence_sufficiency")
    @classmethod
    def valid_sufficiency(cls, value: str) -> str:
        if value not in {"SUFFICIENT", "INSUFFICIENT", "UNCERTAIN"}:
            raise ValueError("invalid evidence sufficiency")
        return value

    @model_validator(mode="after")
    def follow_up_fields(self) -> "AnalysisResult":
        if self.needs_follow_up and (not self.follow_up_reason.strip() or not self.follow_up_question.strip()):
            raise ValueError("follow-up reason and question are required")
        return self


class GeneratedQuestion(BaseModel):
    content: str = Field(min_length=1)
    covered_competency_ids: list[str] = Field(min_length=1, max_length=3)
    turn_type: str = "MAIN_QUESTION"
    evaluation_target: str | None = None
    expected_evidence: list[str] = Field(default_factory=list)
    background_reference: dict[str, str] | None = None

    @field_validator("turn_type")
    @classmethod
    def valid_turn_type(cls, value: str) -> str:
        if value not in {"MAIN_QUESTION", "FOLLOW_UP"}:
            raise ValueError("invalid question turn type")
        return value

    @field_validator("covered_competency_ids")
    @classmethod
    def valid_ids(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value) or len(set(value)) != len(value):
            raise ValueError("covered competency IDs must be unique and non-empty")
        return value

    @field_validator("background_reference")
    @classmethod
    def valid_background_reference(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        if value is None:
            return None
        required = {"source_type", "item_id", "item_type", "display_summary"}
        if set(value) != required or value["source_type"] != "BACKGROUND_ONLY":
            raise ValueError("invalid background reference")
        if value["item_type"] not in {"education", "project", "skill", "experience"}:
            raise ValueError("invalid background reference item type")
        if any(not isinstance(item, str) or not item.strip() for item in value.values()):
            raise ValueError("background reference fields must be non-empty strings")
        if len(value["display_summary"]) > 500:
            raise ValueError("background reference summary is too long")
        return value


class ValidatedAnalysis(AnalysisResult):
    pass


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", "", value)


def validate_source_excerpt(answer: str, excerpt: str) -> bool:
    if not answer or not excerpt:
        return False
    return excerpt in answer or _normalize_whitespace(excerpt) in _normalize_whitespace(answer)


def validate_analysis(result: AnalysisResult | dict[str, Any], answer: str, competency_id: str) -> ValidatedAnalysis:
    try:
        parsed = result if isinstance(result, AnalysisResult) else AnalysisResult.model_validate(result)
    except Exception as exc:
        raise InvalidAIResponse("AI 分析结果不符合结构化契约") from exc
    if any(item.competency_id != competency_id for item in parsed.evidence):
        raise InvalidAIResponse("AI 引用了当前题目之外的能力项")
    observations = []
    had_ungrounded_excerpt = False
    for item in parsed.evidence:
        if validate_source_excerpt(answer, item.excerpt):
            # Preserve a literal answer substring for persistence.  A model
            # may vary whitespace (for example, insert a newline), but the
            # stored observation must still be directly traceable to answer.
            observations.append(
                item
                if item.excerpt in answer
                else item.model_copy(update={"excerpt": answer.strip()})
            )
        else:
            # Never persist model text that cannot be located in the submitted
            # answer (in particular, text copied from an optional resume).
            had_ungrounded_excerpt = True
            grounded_excerpt = answer.strip()
            if grounded_excerpt:
                observations.append(
                    item.model_copy(
                        update={
                            "type": EvidenceType.UNCERTAIN,
                            "excerpt": grounded_excerpt,
                            "validation_note": "引用片段未在回答原文中定位；已降级为待澄清证据",
                        }
                    )
                )
    values = {**parsed.model_dump(), "evidence": [item.model_dump() for item in observations]}
    if had_ungrounded_excerpt:
        # A resume/answer discrepancy is uncertainty, not a negative finding.
        values.update(
            {
                "evidence_sufficiency": "UNCERTAIN",
                "needs_follow_up": True,
                "follow_up_reason": "回答与背景信息存在需要澄清的差异",
                "follow_up_question": "为了准确记录这段经历，请你补充说明其中由你本人负责的具体工作、判断依据和结果。",
            }
        )
        values["evidence"] = [
            {**item, "type": EvidenceType.UNCERTAIN.value}
            for item in values["evidence"]
        ]
    # Provider output must not turn a background discrepancy into an adverse
    # judgment.  Keep negative observations only when their excerpt is fully
    # grounded in the candidate's answer.
    return ValidatedAnalysis.model_validate(values)


def _parse_provider_response(
    body: str,
    model: type[BaseModel],
    *,
    analysis_competency_id: str | None = None,
) -> BaseModel:
    try:
        payload = json.loads(body)
        content = payload["choices"][0]["message"]["content"]
        if isinstance(content, str):
            content = json.loads(content)
        if model is AnalysisResult and isinstance(content, dict):
            normalized_evidence = []
            for item in content.get("evidence", []) or []:
                if not isinstance(item, dict):
                    continue
                raw_type = str(item.get("type", "UNCERTAIN")).upper()
                normalized_type = {
                    "DIRECT": EvidenceType.POSITIVE.value,
                    "POSITIVE": EvidenceType.POSITIVE.value,
                    "NEGATIVE": EvidenceType.NEGATIVE.value,
                    "MISSING": EvidenceType.MISSING.value,
                    "UNCERTAIN": EvidenceType.UNCERTAIN.value,
                }.get(raw_type, EvidenceType.UNCERTAIN.value)
                normalized_evidence.append(
                    {
                        "competency_id": item.get("competency_id") or analysis_competency_id or "",
                        "type": normalized_type,
                        "excerpt": str(item.get("excerpt") or ""),
                        "summary": str(item.get("summary") or item.get("reason") or ""),
                        "confidence": float(item.get("confidence", 0.8 if normalized_type == EvidenceType.POSITIVE.value else 0.5)),
                    }
                )
            content = {**content, "evidence": normalized_evidence}
        return model.model_validate(content)
    except Exception as exc:
        raise RetryableAIError("AI 返回无效 JSON 或不符合 Schema") from exc


def _call_structured(
    system_prompt: str,
    user_payload: dict[str, Any],
    response_model: type[BaseModel],
    transport: Callable[..., Any] | None = None,
    *,
    analysis_competency_id: str | None = None,
) -> BaseModel:
    api_key = get_llm_api_key()
    if not api_key:
        raise RetryableAIError("未配置 AI API Key")
    request_payload = {"model": settings.llm_model, "temperature": 0.2, "response_format": {"type": "json_object"}, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)}]}
    started = time.perf_counter()
    try:
        if transport:
            raw = transport(request_payload, api_key=api_key)
        else:
            request = Request(settings.llm_base_url.rstrip("/") + "/v1/chat/completions", data=json.dumps(request_payload).encode(), headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
            with urlopen(request, timeout=30) as response:
                raw = response.read().decode()
        return _parse_provider_response(
            raw if isinstance(raw, str) else json.dumps(raw),
            response_model,
            analysis_competency_id=analysis_competency_id,
        )
    except RetryableAIError:
        raise
    except Exception as exc:
        raise RetryableAIError(f"AI 调用失败（{round((time.perf_counter() - started) * 1000)}ms）") from exc


def generate_main_question(
    snapshot: Any,
    competencies: list[Any],
    jd_evidence: list[Any],
    transcript: list[Any],
    transport: Callable[..., Any] | None = None,
    *,
    agent_context: dict[str, Any] | None = None,
    resume_reference: Any | None = None,
) -> GeneratedQuestion:
    from .assessment_prompts import build_question_prompt
    ids = [item.id for item in competencies]
    if not 1 <= len(ids) <= 3:
        raise InvalidAIResponse("题目必须覆盖 1 至 3 个能力项")
    if len(set(ids)) != len(ids):
        raise InvalidAIResponse("题目覆盖能力项不能重复")
    snapshot_ids = {item.id for item in snapshot.competencies}
    if not set(ids).issubset(snapshot_ids):
        raise InvalidAIResponse("题目包含确认快照之外的能力项")
    competency_payload = [asdict(item) if is_dataclass(item) else dict(item) for item in competencies]
    result = _call_structured(
        build_question_prompt(competencies, jd_evidence, transcript, resume_reference=resume_reference),
        {
            "model_version_id": snapshot.model_version_id,
            "competencies": competency_payload,
            "jd_evidence": jd_evidence,
            "transcript": transcript,
            "agent_context": agent_context or {},
            "resume_reference": (
                resume_reference.model_dump(mode="json")
                if hasattr(resume_reference, "model_dump")
                else resume_reference
            ),
        },
        GeneratedQuestion,
        transport,
    )
    if result.covered_competency_ids != ids or result.turn_type != "MAIN_QUESTION":
        raise InvalidAIResponse("AI 修改了题目覆盖能力范围")
    if resume_reference is None and result.background_reference is not None:
        raise InvalidAIResponse("AI 虚构了背景引用")
    formal_target = (agent_context or {}).get("formal_target") or {}
    if formal_target:
        if result.evaluation_target != formal_target.get("question_goal"):
            raise InvalidAIResponse("AI 修改了正式评估目标")
        if result.expected_evidence != list(formal_target.get("expected_evidence", [])):
            raise InvalidAIResponse("AI 修改了正式证据目标")
    if resume_reference is not None:
        reference = resume_reference.model_dump(mode="json") if hasattr(resume_reference, "model_dump") else resume_reference
        if result.background_reference is not None:
            expected_summary = str(reference.get("prompt_hint", ""))[:500]
            if result.background_reference.get("source_type") != "BACKGROUND_ONLY" or result.background_reference.get("item_id") != reference.get("item_id") or result.background_reference.get("item_type") != reference.get("item_type") or result.background_reference.get("display_summary") != expected_summary:
                raise InvalidAIResponse("AI 修改或虚构了背景引用")
        else:
            result = result.model_copy(update={"background_reference": {"source_type": "BACKGROUND_ONLY", "item_id": reference["item_id"], "item_type": reference["item_type"], "display_summary": reference.get("prompt_hint", "")[:500]}})
    return result


def analyze_answer(snapshot: Any, competency: Any, jd_evidence: list[Any], transcript: list[Any], answer: str, transport: Callable[..., Any] | None = None) -> ValidatedAnalysis:
    from .assessment_prompts import build_analysis_prompt
    if competency.id not in {item.id for item in snapshot.competencies}:
        raise InvalidAIResponse("分析能力项不属于确认快照")
    competency_payload = asdict(competency) if is_dataclass(competency) else dict(competency)
    def demo_analysis() -> ValidatedAnalysis:
        # The local/demo workflow must remain usable without a provider key or
        # when a configured provider is unavailable. Keep this adapter
        # deterministic and grounded entirely in the submitted answer.
        text = answer.strip()
        refusal = re.search(r"^(我不会|不会|不知道|没有经验|暂无经验|不清楚)[。！!，,、\s]*$", text) is not None
        sufficient = len(text) >= 12 and not refusal
        result = AnalysisResult(
            answer_summary=text or "未提供回答",
            evidence=[
                EvidenceResult(
                    competency_id=competency.id,
                    type=EvidenceType.POSITIVE if sufficient else EvidenceType.UNCERTAIN,
                    excerpt=text,
                    summary="演示模式基于回答原文保留证据",
                    confidence=0.6 if sufficient else 0.3,
                    validation_note=None if text else "回答为空",
                )
            ] if text else [],
            evidence_sufficiency="SUFFICIENT" if sufficient else "INSUFFICIENT",
            needs_follow_up=not sufficient,
            follow_up_reason="需要更多具体做法、依据和结果" if not sufficient else "",
            follow_up_question=f"请具体说明你在{competency.name}中的做法、依据和结果" if not sufficient else "",
        )
        return validate_analysis(result, answer, competency.id)

    # Offline/demo mode is explicit when analysis is disabled or no provider
    # key is configured.  Once a configured provider is enabled, failures must
    # remain retryable instead of being disguised as a length-based result.
    if not is_llm_analysis_enabled() or not get_llm_api_key():
        return demo_analysis()
    result = _call_structured(
        build_analysis_prompt(competency, jd_evidence, transcript),
        {
            "model_version_id": snapshot.model_version_id,
            "competency": competency_payload,
            "jd_evidence": jd_evidence,
            "answer": answer,
            "transcript": transcript,
        },
        AnalysisResult,
        transport,
        analysis_competency_id=competency.id,
    )
    return validate_analysis(result, answer, competency.id)
