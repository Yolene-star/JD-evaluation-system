from backend.app.services.parsing import parse_jd
from backend.app.services.weights import calculate_competency_weight, normalize_weights


def test_parser_creates_evidence_for_each_competency() -> None:
    parsed = parse_jd("负责 React 组件开发，优化页面性能")
    assert {item.name for item in parsed.competencies} == {"组件化开发", "性能优化"}
    assert all(item.evidence_ids for item in parsed.competencies)
    assert all(item.start_offset < item.end_offset for item in parsed.competencies)


def test_weight_formula_normalizes_to_one() -> None:
    values = [calculate_competency_weight(.8, .9, .7, .6), calculate_competency_weight(.5, .4, .5, .4)]
    assert abs(sum(normalize_weights(values)) - 1.0) < 1e-9
