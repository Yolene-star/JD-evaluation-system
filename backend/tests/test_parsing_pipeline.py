import json

from backend.app.services.parsing import parse_jd
from backend.app.services.ai_parsing import parse_jd_with_llm
from backend.app.services.weights import calculate_competency_weight, normalize_weights


def test_parser_creates_evidence_for_each_competency() -> None:
    parsed = parse_jd("负责 React 组件开发，优化页面性能")
    assert {item.name for item in parsed.competencies} == {"组件化开发", "性能优化"}
    assert all(item.evidence_ids for item in parsed.competencies)
    assert all(item.start_offset < item.end_offset for item in parsed.competencies)


def test_weight_formula_normalizes_to_one() -> None:
    values = [calculate_competency_weight(.8, .9, .7, .6), calculate_competency_weight(.5, .4, .5, .4)]
    assert abs(sum(normalize_weights(values)) - 1.0) < 1e-9


def test_llm_parser_returns_traceable_competencies(monkeypatch) -> None:
    text = "参与智能体产品的后端开发工作，使用 LangChain 和 Dify 开发智能体功能。"

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def read(self):
            body = {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "competencies": [{
                                "name": "智能体后端开发",
                                "description": "设计并实现智能体后端模块",
                                "evidence_excerpt": "参与智能体产品的后端开发工作",
                            }],
                            "requirements": [],
                            "constraints": [],
                        }, ensure_ascii=False),
                    },
                }],
            }
            return json.dumps(body, ensure_ascii=False).encode("utf-8")

    monkeypatch.setattr("backend.app.services.ai_parsing.urlopen", lambda *args, **kwargs: FakeResponse())
    parsed, source, _, error = parse_jd_with_llm(text, api_key="test-key")

    assert source == "llm"
    assert error is None
    assert parsed.competencies[0].name == "智能体后端开发"
    assert parsed.competencies[0].excerpt == "参与智能体产品的后端开发工作"
    assert text[parsed.competencies[0].start_offset:parsed.competencies[0].end_offset] == parsed.competencies[0].excerpt


def test_llm_parser_rejects_untraceable_evidence_and_falls_back(monkeypatch) -> None:
    text = "负责 React 组件开发。"

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def read(self):
            body = {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "competencies": [{
                                "name": "组件化开发",
                                "description": "构建可复用组件",
                                "evidence_excerpt": "原文中不存在的证据",
                            }],
                            "requirements": [],
                            "constraints": [],
                        }, ensure_ascii=False),
                    },
                }],
            }
            return json.dumps(body, ensure_ascii=False).encode("utf-8")

    monkeypatch.setattr("backend.app.services.ai_parsing.urlopen", lambda *args, **kwargs: FakeResponse())
    parsed, source, _, error = parse_jd_with_llm(text, api_key="test-key")

    assert source == "deterministic-fallback"
    assert error is not None
    assert parsed.competencies[0].name == "组件化开发"
