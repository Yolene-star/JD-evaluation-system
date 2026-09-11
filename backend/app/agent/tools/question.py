from collections.abc import Callable
import inspect
from typing import Any
from pydantic import ValidationError

from ...services.assessment_ai import GeneratedQuestion, InvalidAIResponse, RetryableAIError, generate_main_question


class QuestionTool:
    def __init__(self, generate_fn: Callable[..., GeneratedQuestion] = generate_main_question) -> None:
        self.generate_fn = generate_fn

    def generate(
        self,
        *,
        snapshot: Any,
        competencies: list[Any],
        jd_evidence: list[Any],
        transcript: list[Any],
        transport: Callable[..., Any] | None = None,
        agent_context: dict[str, Any] | None = None,
        resume_reference: Any | None = None,
    ) -> GeneratedQuestion:
        kwargs = {"agent_context": agent_context}
        try:
            parameters = inspect.signature(self.generate_fn).parameters
            if "resume_reference" in parameters or any(item.kind is inspect.Parameter.VAR_KEYWORD for item in parameters.values()):
                kwargs["resume_reference"] = resume_reference
        except (TypeError, ValueError):
            pass
        try:
            return self.generate_fn(snapshot, competencies, jd_evidence, transcript, transport, **kwargs)
        except (InvalidAIResponse, ValidationError):
            target = competencies[0]
            formal = (agent_context or {}).get("formal_target") or {}
            return GeneratedQuestion(
                content=f"请描述一次与你目标岗位相关的实际项目经历，重点说明你在{getattr(target, 'name', target.id)}中的具体做法、依据和结果。",
                covered_competency_ids=[target.id],
                turn_type="MAIN_QUESTION",
                evaluation_target=formal.get("question_goal"),
                expected_evidence=list(formal.get("expected_evidence", [])),
            )

    def generate_follow_up(
        self,
        *,
        competency: Any,
        analysis: Any,
        **_kwargs: Any,
    ) -> GeneratedQuestion:
        content = str(getattr(analysis, "follow_up_question", "") or "").strip()
        if not content:
            content = f"请补充说明你在{getattr(competency, 'name', competency.id)}中的具体做法、依据和结果。"
        return GeneratedQuestion(
            content=content,
            covered_competency_ids=[competency.id],
            turn_type="FOLLOW_UP",
            evaluation_target=analysis.follow_up_reason or None,
        )
