import json
import os
import time
from urllib.request import Request, urlopen

from ..config import get_llm_api_key, settings


class LLMUnavailable(RuntimeError):
    pass


def _fallback(project_name: str, project_status: str, message: str, context: dict | None = None) -> str:
    jd_count = len((context or {}).get("jds", []))
    evidence_count = len((context or {}).get("evidence", []))
    return f"项目“{project_name}”当前处于 {project_status}，已有 {jd_count} 份 JD、{evidence_count} 条证据。我理解你说的是“{message}”。你可以让我解释某项能力的依据、检查解析状态，或继续添加材料。"


def generate_reply(project_name: str, project_status: str, message: str, context: dict | None = None, api_key: str | None = None) -> tuple[str, str, int | None, str | None]:
    api_key = get_llm_api_key(api_key)
    if not api_key:
        return _fallback(project_name, project_status, message, context), "demo-fallback", None, None
    url = settings.llm_base_url.rstrip("/") + "/v1/chat/completions"
    payload = {"model": settings.llm_model, "temperature": 0.2, "messages": [{"role": "system", "content": "你是岗位胜任力测评系统的主Agent。只依据给定项目事实回答，不修改状态；回答要具体、自然，并在涉及证据时引用证据 ID。"}, {"role": "user", "content": json.dumps({"project": project_name, "status": project_status, "message": message, "context": context or {}}, ensure_ascii=False)}]}
    started = time.perf_counter()
    try:
        request = Request(url, data=json.dumps(payload).encode(), headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
        with urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode())
        reply = body["choices"][0]["message"]["content"]
        return reply, "llm", round((time.perf_counter() - started) * 1000), None
    except Exception as exc:
        return _fallback(project_name, project_status, message, context), "llm-error", round((time.perf_counter() - started) * 1000), str(exc)[:300]
