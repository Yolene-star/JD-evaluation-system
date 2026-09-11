from backend.app.services.scoring import score_competency


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
