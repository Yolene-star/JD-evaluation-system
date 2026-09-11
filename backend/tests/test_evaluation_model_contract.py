from backend.app.services.aggregation import aggregate_competencies


def test_aggregation_preserves_and_deduplicates_evaluation_fields():
    rows = aggregate_competencies([
        {
            "name": "模型优化能力",
            "jd_id": "jd-1",
            "weight": 1,
            "evidence_ids": ["e-1"],
            "indicators": ["说明方案依据", "解释结果"],
            "evidence_requirements": ["本人工作", "结果指标"],
        },
        {
            "name": "模型优化能力",
            "jd_id": "jd-2",
            "weight": 1,
            "evidence_ids": ["e-1", "e-2"],
            "indicators": ["解释结果", "说明边界"],
            "evidence_requirements": ["结果指标", "对比方案"],
        },
    ])
    assert rows[0]["indicators"] == ["说明方案依据", "解释结果", "说明边界"]
    assert rows[0]["evidence_requirements"] == ["本人工作", "结果指标", "对比方案"]
    assert rows[0]["evidence_ids"] == ["e-1", "e-2"]


def test_aggregation_defaults_new_evaluation_fields_for_legacy_rows():
    row = aggregate_competencies([{"name": "系统设计", "jd_id": "jd-1", "weight": 1}])[0]
    assert row["indicators"] == []
    assert row["evidence_requirements"] == []
