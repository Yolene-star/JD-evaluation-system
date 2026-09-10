from dataclasses import dataclass, field
from typing import Any


@dataclass
class CompetencyScore:
    competency_id: str
    status: str
    score: float | None
    attainment: float | None
    level: str | None
    evidence_ids: list[str] = field(default_factory=list)
    matched_indicator_ids: list[str] = field(default_factory=list)
    negative_evidence_ids: list[str] = field(default_factory=list)
    missing_indicator_ids: list[str] = field(default_factory=list)
    confidence: float | None = None
    rationale: str = ""


@dataclass
class EvidencePackageScore:
    evaluations: list[CompetencyScore]
    evaluated_weight: float
    unevaluated_weight: float
    match_score: float | None
    match_score_type: str


def _value(item: Any, key: str, default: Any = None) -> Any:
    return item.get(key, default) if isinstance(item, dict) else getattr(item, key, default)


def score_competency(*, competency_id: str, status: str, rubric: dict, observations: list[dict]) -> CompetencyScore:
    status = getattr(status, "value", status)
    evidence_ids = [str(_value(obs, "id")) for obs in observations if _value(obs, "id") is not None]
    if status == "INCOMPLETE":
        return CompetencyScore(competency_id, status, None, None, None, evidence_ids=evidence_ids, confidence=None, rationale="能力项测评尚未完成，暂不可完全评价")
    indicators = list(_value(rubric, "indicators", []) or [])
    if not indicators:
        indicators = [f"indicator-{index + 1}" for index in range(max(1, len(observations)))]
    positive = [obs for obs in observations if getattr(_value(obs, "type", ""), "value", _value(obs, "type", "")) == "POSITIVE"]
    negative = [obs for obs in observations if getattr(_value(obs, "type", ""), "value", _value(obs, "type", "")) == "NEGATIVE"]
    missing = [obs for obs in observations if getattr(_value(obs, "type", ""), "value", _value(obs, "type", "")) == "MISSING"]
    uncertain = [obs for obs in observations if getattr(_value(obs, "type", ""), "value", _value(obs, "type", "")) == "UNCERTAIN"]
    # Observations are the available indicator evidence when the adapter has
    # not supplied explicit indicator IDs.  Negative and missing observations
    # therefore reduce coverage without fabricating a claim of coverage.
    evidence_denominator = len(positive) + len(negative) + len(missing)
    coverage = min(1.0, len(positive) / max(len(indicators), evidence_denominator or 0, 1))
    if coverage <= 0:
        low, high, level = 0, 2, "0-2"
    elif coverage < 0.5:
        low, high, level = 3, 4, "3-4"
    elif coverage < 0.75:
        low, high, level = 5, 6, "5-6"
    elif coverage < 1.0:
        low, high, level = 7, 8, "7-8"
    else:
        low, high, level = 9, 10, "9-10"
    score = round(coverage * 10, 1)
    score = float(max(0.0, min(10.0, score)))
    confidence = max(0.0, min(1.0, (sum(float(_value(obs, "confidence", 0.0) or 0.0) for obs in observations) / len(observations) if observations else 0.0) * (1 - 0.25 * min(1, len(uncertain)))))
    matched_ids = [str(_value(obs, "id")) for obs in positive]
    negative_ids = [str(_value(obs, "id")) for obs in negative]
    missing_ids = [str(_value(obs, "id")) for obs in missing]
    return CompetencyScore(competency_id, status, score, round(score / 10, 4), level, evidence_ids, matched_ids, negative_ids, missing_ids, round(confidence, 4), f"覆盖 {len(positive)}/{len(indicators)} 项指标")


def score_evidence_package(package: dict, rubrics: dict[str, dict]) -> EvidencePackageScore:
    evaluations: list[CompetencyScore] = []
    evaluated_weight = 0.0
    unevaluated_weight = 0.0
    weighted_score = 0.0
    for item in package.get("competencies", []):
        competency_id = str(_value(item, "competency_id"))
        weight = float(_value(item, "weight", _value(rubrics.get(competency_id, {}), "weight", 0.0)) or 0.0)
        result = score_competency(competency_id=competency_id, status=str(getattr(_value(item, "status", "INCOMPLETE"), "value", _value(item, "status", "INCOMPLETE"))), rubric=rubrics.get(competency_id, {}), observations=list(_value(item, "observations", []) or []))
        evaluations.append(result)
        if result.score is None:
            unevaluated_weight += weight
        else:
            evaluated_weight += weight
            weighted_score += result.score * weight
    match_type = "FULL" if str(package.get("completion")) == "FULL" and evaluated_weight > 0 else ("PARTIAL" if evaluated_weight > 0 else "NONE")
    match_score = round(weighted_score / evaluated_weight / 10 * 100, 1) if evaluated_weight > 0 else None
    return EvidencePackageScore(evaluations, evaluated_weight, unevaluated_weight, match_score, match_type)
