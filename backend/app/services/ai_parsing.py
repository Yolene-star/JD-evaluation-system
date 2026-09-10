import json
import time
from typing import Any
from urllib.request import Request, urlopen

from ..config import get_llm_api_key, settings
from .parsing import ParsedCompetency, ParsedJd, parse_jd


PROMPT_VERSION = "stage1-jd-analysis-v1"


def _fallback(text: str, started: float, error: str) -> tuple[ParsedJd, str, int, str]:
    latency = round((time.perf_counter() - started) * 1000)
    return parse_jd(text), "deterministic-fallback", latency, error[:300]


def _content_json(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    value = json.loads(cleaned)
    if not isinstance(value, dict):
        raise ValueError("模型输出不是 JSON 对象")
    return value


def _strings(value: Any, *, limit: int = 1000) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    result: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            result.append(item.strip()[:limit])
    return tuple(result)


def _validated_result(text: str, value: dict[str, Any]) -> ParsedJd:
    rows = value.get("competencies")
    if not isinstance(rows, list):
        raise ValueError("模型输出缺少 competencies 数组")
    competencies: list[ParsedCompetency] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()[:100]
        description = str(row.get("description") or "").strip()[:1000]
        excerpt = str(row.get("evidence_excerpt") or "").strip()[:1000]
        start = text.find(excerpt) if excerpt else -1
        if not name or not description or start < 0 or name in seen:
            continue
        seen.add(name)
        competencies.append(ParsedCompetency(
            name=name,
            evidence_ids=(),
            excerpt=excerpt,
            start_offset=start,
            end_offset=start + len(excerpt),
            description=description,
        ))
    if not competencies:
        raise ValueError("模型未返回具有可回溯原文证据的能力项")
    return ParsedJd(
        competencies=tuple(competencies),
        qualifications=_strings(value.get("requirements")),
        constraints=_strings(value.get("constraints")),
    )


def parse_jd_with_llm(
    text: str,
    *,
    api_key: str | None = None,
) -> tuple[ParsedJd, str, int | None, str | None]:
    """Extract JD facts with an OpenAI-compatible model and validate every evidence quote."""
    started = time.perf_counter()
    resolved_key = get_llm_api_key(api_key)
    if not resolved_key:
        return parse_jd(text), "deterministic-fallback", None, "未配置 LLM API Key"

    url = settings.llm_base_url.rstrip("/") + "/v1/chat/completions"
    schema_instruction = {
        "competencies": [{
            "name": "简洁、规范的能力名称",
            "description": "该能力在岗位中的具体含义",
            "evidence_excerpt": "必须逐字复制自 JD 原文的连续片段",
        }],
        "requirements": ["学历、经验、资历等要求的原文短句"],
        "constraints": ["地点、出差、工作制等约束的原文短句"],
    }
    payload = {
        "model": settings.llm_model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是岗位 JD 结构化抽取器。只依据用户提供的 JD 原文抽取岗位能力、资历要求和约束。"
                    "不得补充原文没有的信息。每个能力必须提供一段逐字复制、连续且足以支持该能力的 evidence_excerpt。"
                    "只返回 JSON，不要 Markdown。输出结构示例："
                    + json.dumps(schema_instruction, ensure_ascii=False)
                ),
            },
            {"role": "user", "content": text},
        ],
    }
    try:
        request = Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {resolved_key}",
                "Content-Type": "application/json",
            },
        )
        with urlopen(request, timeout=45) as response:
            body = json.loads(response.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        parsed = _validated_result(text, _content_json(content))
        latency = round((time.perf_counter() - started) * 1000)
        return parsed, "llm", latency, None
    except Exception as exc:
        return _fallback(text, started, str(exc))
