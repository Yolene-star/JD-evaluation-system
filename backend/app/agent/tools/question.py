from collections.abc import Callable
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
    ) -> GeneratedQuestion:
        return self.generate_fn(
            snapshot,
            competencies,
            jd_evidence,
            transcript,
            transport,
            agent_context=agent_context,
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
