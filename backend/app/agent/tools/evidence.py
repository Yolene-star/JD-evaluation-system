from collections.abc import Callable
from typing import Any

from ...services.assessment_ai import ValidatedAnalysis, analyze_answer


class EvidenceTool:
    def __init__(self, analyze_fn: Callable[..., ValidatedAnalysis] = analyze_answer) -> None:
        self.analyze_fn = analyze_fn

    def analyze(
        self,
        *,
        snapshot: Any,
        competency: Any,
        jd_evidence: list[Any],
        transcript: list[Any],
        answer: str,
        transport: Callable[..., Any] | None = None,
    ) -> ValidatedAnalysis:
        return self.analyze_fn(
            snapshot,
            competency,
            jd_evidence,
            transcript,
            answer,
            transport,
        )
