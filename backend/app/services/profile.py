from __future__ import annotations

from typing import Any, Callable

from .profile_prompts import PROFILE_PROMPT_VERSION


class NarrativeValidationError(ValueError):
    pass


def generate_profile_narrative(facts: dict[str, Any], adapter: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
    """Call a provider with score facts only and validate citation references."""
    result = adapter({"prompt_version": PROFILE_PROMPT_VERSION, "facts": facts})
    if not isinstance(result, dict):
        raise NarrativeValidationError("narrative must be an object")
    allowed = set(facts.get("evidence_ids", []))
    cited = result.get("cited_evidence_ids", result.get("evidence_ids", [])) or []
    nested_citations = []
    for group in ("strengths", "weaknesses", "recommendations"):
        for item in result.get(group, []) or []:
            if isinstance(item, dict):
                nested_citations.extend(item.get("evidence_ids", item.get("evidenceIds", [])) or [])
    all_citations = [*cited, *nested_citations]
    if any(str(item) not in allowed for item in all_citations):
        raise NarrativeValidationError("narrative cited unknown evidence")
    return {
        "overview": str(result.get("overview", result.get("text", ""))),
        "strengths": list(result.get("strengths", []) or []),
        "weaknesses": list(result.get("weaknesses", []) or []),
        "recommendations": list(result.get("recommendations", []) or []),
        "cited_evidence_ids": [str(item) for item in cited],
    }
