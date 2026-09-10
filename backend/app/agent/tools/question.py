from collections.abc import Callable
import inspect
from typing import Any

from ...services.assessment_ai import GeneratedQuestion, generate_main_question


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
        return self.generate_fn(
            snapshot,
            competencies,
            jd_evidence,
            transcript,
            transport,
            **kwargs,
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
