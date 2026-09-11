from backend.app.services.scoring import score_competency
from backend.app.services.scoring import score_evidence_package


def test_score_exposes_matched_and_missing_indicator_explanations():
    result = score_competency(
        competency_id="c1",
        status="SUFFICIENT",
        rubric={"indicators": ["方案依据", "结果指标"]},
        observations=[
            {"id": "e1", "type": "POSITIVE", "confidence": 0.9,
             "matched_indicator_ids": ["方案依据"]},
        ],
    )
    assert result.matched_indicator_ids == ["方案依据"]
    assert result.missing_indicator_ids == ["结果指标"]


def test_package_level_indicator_explanations_are_consumed_by_scoring():
    score = score_evidence_package({"completion": "FULL", "competencies": [{
        "competency_id": "c1", "status": "SUFFICIENT", "weight": 1,
        "matched_indicators": ["方案依据"], "missing_indicators": ["结果指标"], "observations": [],
    }]}, {"c1": {"weight": 1, "indicators": ["方案依据", "结果指标"]}})
    assert score.evaluations[0].matched_indicator_ids == ["方案依据"]
    assert score.evaluations[0].missing_indicator_ids == ["结果指标"]
