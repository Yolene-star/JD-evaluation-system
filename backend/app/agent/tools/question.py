from collections.abc import Callable
import inspect
from typing import Any

from ...services.assessment_ai import GeneratedQuestion, RetryableAIError, generate_main_question


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
            return self.generate_fn(
                snapshot,
                competencies,
                jd_evidence,
                transcript,
                transport,
                **kwargs,
            )
        except RetryableAIError:
            target = (agent_context or {}).get("formal_target") or {}
            competency = competencies[0]
            reference = resume_reference
            metadata = None
            if reference is not None:
                metadata = {
                    "source_type": "BACKGROUND_ONLY",
                    "item_id": reference.item_id,
                    "item_type": reference.item_type,
                    "display_summary": reference.prompt_hint[:500],
                }
            return GeneratedQuestion(
                content=(
                    f"请描述一次与你目标岗位相关的实际项目经历，重点说明你在{competency.name}中的具体做法、依据和结果。"
                    if reference is None
                    else f"{reference.prompt_hint}请说明其中与你{competency.name}相关的具体做法、依据和结果。"
                ),
                covered_competency_ids=[item.id for item in competencies],
                turn_type="MAIN_QUESTION",
                evaluation_target=target.get("question_goal"),
                expected_evidence=list(target.get("expected_evidence", [])),
                background_reference=metadata,
            )

    def generate_follow_up(
        self,
        *,
        competency: Any,
        analysis: Any,
        **_kwargs: Any,
    ) -> GeneratedQuestion:
        return GeneratedQuestion(
            content=analysis.follow_up_question,
            covered_competency_ids=[competency.id],
            turn_type="FOLLOW_UP",
            evaluation_target=analysis.follow_up_reason or None,
        )
