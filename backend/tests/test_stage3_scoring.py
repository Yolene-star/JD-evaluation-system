import pytest

from backend.app.services.scoring import score_evidence_package, score_competency


def rubric(competency_id="c1"):
    return {"competency_id": competency_id, "indicators": ["i1", "i2", "i3", "i4"]}


def observation(kind, evidence_id):
    return {"id": evidence_id, "type": kind, "excerpt": evidence_id, "summary": evidence_id, "confidence": 0.8}


def test_score_competency_uses_five_bands_and_negative_deduction_with_traceability() -> None:
    result = score_competency(
        competency_id="c1",
        status="SUFFICIENT",
        rubric=rubric(),
        observations=[observation("POSITIVE", "e1"), observation("POSITIVE", "e2"), observation("POSITIVE", "e3"), observation("MISSING", "e4"), observation("NEGATIVE", "e5")],
    )
    assert result.score == 6
    assert result.attainment == 0.6
    assert result.level == "5-6"
    assert result.evidence_ids == ["e1", "e2", "e3", "e4", "e5"]
    assert result.negative_evidence_ids == ["e5"]


def test_incomplete_is_not_scored() -> None:
    result = score_competency(competency_id="c1", status="INCOMPLETE", rubric=rubric(), observations=[])
    assert result.score is None
    assert result.attainment is None
    assert result.status == "INCOMPLETE"


def test_match_score_full_and_partial_reweight_and_none() -> None:
    package = {
        "completion": "PARTIAL",
        "competencies": [
            {"competency_id": "c1", "status": "SUFFICIENT", "weight": 0.75, "observations": [observation("POSITIVE", "e1")]},
            {"competency_id": "c2", "status": "INCOMPLETE", "weight": 0.25, "observations": []},
        ],
    }
    rubrics = {"c1": rubric("c1"), "c2": rubric("c2")}
    result = score_evidence_package(package, rubrics)
    assert result.match_score_type == "PARTIAL"
    assert result.evaluated_weight == 0.75
    assert result.unevaluated_weight == 0.25
    assert result.match_score == 25.0
    empty = score_evidence_package({"completion": "PARTIAL", "competencies": [{"competency_id": "c1", "status": "INCOMPLETE", "weight": 1.0, "observations": []}]}, {"c1": rubric("c1")})
    assert empty.match_score is None
    assert empty.match_score_type == "NONE"
