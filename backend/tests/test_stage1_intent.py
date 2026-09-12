import json

from backend.app.services.stage1_intent import interpret_stage1_intent


def test_llm_intent_accepts_lowercase_tool_names_from_openai_compatible_api(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def read(self):
            content = json.dumps({"tool": "rename_jd", "arguments": {"jd_title": "前端 JD", "new_title": "高级前端 JD"}, "confidence": 0.96})
            return json.dumps({"choices": [{"message": {"content": content}}]}).encode()

    monkeypatch.setattr("backend.app.services.stage1_intent.get_llm_api_key", lambda explicit=None: "test-key")
    monkeypatch.setattr("backend.app.services.stage1_intent.urlopen", lambda *args, **kwargs: FakeResponse())

    intent, source, _, error = interpret_stage1_intent(
        "麻烦把这个岗位标题换成高级前端 JD",
        {"jds": [{"title": "前端 JD"}], "competency_names": []},
    )

    assert error is None
    assert source == "llm-tool"
    assert intent.tool == "RENAME_JD"
    assert intent.arguments["new_title"] == "高级前端 JD"
