from collections.abc import Callable
from typing import Any

from ...services.scoring import EvidencePackageScore, score_evidence_package


class ScoringTool:
    def __init__(
        self,
        score_fn: Callable[[dict, dict[str, dict]], EvidencePackageScore] = score_evidence_package,
    ) -> None:
        self.score_fn = score_fn

    def score(self, package: dict, rubrics: dict[str, dict]) -> EvidencePackageScore:
        return self.score_fn(package, rubrics)
