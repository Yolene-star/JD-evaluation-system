from backend.app.services.assessment_ai import AnalysisResult


def test_analysis_result_exposes_indicator_and_requirement_gaps():
    result = AnalysisResult(
        answer_summary="回答了方案选择",
        evidence=[],
        evidence_sufficiency="INSUFFICIENT",
        needs_follow_up=True,
        follow_up_reason="缺少结果",
        follow_up_question="结果如何？",
        matched_indicators=["说明方案依据"],
        matched_evidence_requirements=["本人工作"],
        missing_evidence_requirements=["结果指标"],
    )
    assert result.matched_indicators == ["说明方案依据"]
    assert result.missing_evidence_requirements == ["结果指标"]
