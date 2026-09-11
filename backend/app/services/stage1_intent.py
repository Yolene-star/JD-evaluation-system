from dataclasses import dataclass, field
import json
import re
import time
from urllib.request import Request, urlopen

from ..config import get_llm_api_key, settings


ALLOWED_TOOLS = {
    "CHAT",
    "DELETE_PROJECT",
    "LIST_JDS",
    "RENAME_JD",
    "REMOVE_JD",
    "READD_JD",
    "ANALYZE_JD",
    "LIST_COMPETENCIES",
    "CREATE_COMPETENCY",
    "UPDATE_COMPETENCY_NAME",
    "UPDATE_COMPETENCY_WEIGHT",
    "DELETE_COMPETENCY",
    "QUERY_EVIDENCE",
    "GENERATE_TOTAL_MODEL",
    "CONFIRM_MODEL",
}


@dataclass(frozen=True)
class Stage1Intent:
    tool: str
    arguments: dict = field(default_factory=dict)
    confidence: float = 1.0


def _mentioned(message: str, values: list[str]) -> str | None:
    matches = [value for value in values if value and value in message]
    if not matches:
        return None
    return max(matches, key=len)


def _clean_name(value: str) -> str:
    return value.strip().strip("《》「」\"'，。,. ")


def parse_stage1_intent(message: str, context: dict) -> Stage1Intent:
    jd_titles = [str(item.get("title", "")) for item in context.get("jds", [])]
    competency_names = [str(item) for item in context.get("competency_names", [])]
    project_name = str(context.get("project_name", ""))
    jd_title = _mentioned(message, jd_titles)
    competency_name = _mentioned(message, competency_names)
    if re.search(r"(?:删除|删掉|移除|归档).*(?:项目|任务)", message) or (project_name and project_name in message and re.search(r"(?:删除|删掉|移除|归档)", message)):
        return Stage1Intent("DELETE_PROJECT", {"project_name": project_name})

    if re.search(r"(?:确认并冻结|冻结模型|确认模型)", message):
        return Stage1Intent("CONFIRM_MODEL")
    if re.search(r"(?:生成|汇总|重新生成).*总模型", message):
        return Stage1Intent("GENERATE_TOTAL_MODEL")
    if re.search(r"(?:查看|查询|列出|有哪些).*(?:能力|模型内容)", message):
        return Stage1Intent("LIST_COMPETENCIES", {"scope": "single" if jd_title else "total", **({"jd_title": jd_title} if jd_title else {})})
    if re.search(r"(?:查看|查询|列出|有哪些).*JD", message, re.IGNORECASE) and not competency_name:
        return Stage1Intent("LIST_JDS")
    if jd_title and not competency_name and re.search(r"(?:改名为|重命名为|名称改为)", message):
        match = re.search(r"(?:改名为|重命名为|名称改为)\s*(.+?)\s*$", message)
        if match:
            return Stage1Intent("RENAME_JD", {"jd_title": jd_title, "new_title": _clean_name(match.group(1))})
    if jd_title and re.search(r"(?:移除|排除|删除).*(?:JD|模型)", message, re.IGNORECASE) and not competency_name:
        return Stage1Intent("REMOVE_JD", {"jd_title": jd_title})
    if jd_title and re.search(r"(?:重新加入|恢复参与|加回)", message):
        return Stage1Intent("READD_JD", {"jd_title": jd_title})
    if re.search(r"(?:重新解析|分析|解析).*(?:JD|岗位)", message, re.IGNORECASE):
        return Stage1Intent("ANALYZE_JD", {"jd_title": jd_title} if jd_title else {})
    if re.search(r"(?:查看|查询|为什么|依据).*(?:证据|原文|相关度|重要性)", message) and competency_name:
        return Stage1Intent("QUERY_EVIDENCE", {"competency_name": competency_name, **({"jd_title": jd_title} if jd_title else {})})
    if re.search(r"(?:新增|添加|创建).*(?:能力|能力项)", message):
        match = re.search(r"(?:新增|添加|创建)\s*(.+?)(?:能力项?|到|至|$)", message)
        if match:
            name = _clean_name(match.group(1))
            if jd_title and name.startswith(jd_title):
                name = name[len(jd_title):].lstrip("中内的 ")
            return Stage1Intent("CREATE_COMPETENCY", {"scope": "single" if jd_title else "total", **({"jd_title": jd_title} if jd_title else {}), "name": name})
    if competency_name and re.search(r"(?:删除|移除).*(?:能力|能力项)", message):
        return Stage1Intent("DELETE_COMPETENCY", {"competency_name": competency_name, "scope": "single" if jd_title else "total", **({"jd_title": jd_title} if jd_title else {})})
    if competency_name and re.search(r"(?:改名为|重命名为|名称改为)", message):
        match = re.search(r"(?:改名为|重命名为|名称改为)\s*(.+?)\s*$", message)
        if match:
            return Stage1Intent("UPDATE_COMPETENCY_NAME", {"competency_name": competency_name, "new_name": _clean_name(match.group(1)), "scope": "single" if jd_title else "total", **({"jd_title": jd_title} if jd_title else {})})
    if competency_name and re.search(r"(?:权重|占比)", message):
        match = re.search(r"(\d+(?:\.\d+)?)\s*%", message)
        if match:
            return Stage1Intent("UPDATE_COMPETENCY_WEIGHT", {"competency_name": competency_name, "value": float(match.group(1)) / 100, "scope": "single" if jd_title else "total", **({"jd_title": jd_title} if jd_title else {})})
    return Stage1Intent("CHAT", confidence=0.0)


def interpret_stage1_intent(message: str, context: dict, api_key: str | None = None) -> tuple[Stage1Intent, str, int | None, str | None]:
    deterministic = parse_stage1_intent(message, context)
    if deterministic.tool != "CHAT":
        return deterministic, "deterministic-tool", None, None
    key = get_llm_api_key(api_key)
    if not key:
        return deterministic, "demo-fallback", None, None
    payload = {
        "model": settings.llm_model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是阶段一意图路由器。只能返回 JSON："
                    '{"tool":"工具名","arguments":{},"confidence":0到1}。'
                    f"允许工具：{sorted(ALLOWED_TOOLS)}。"
                    "只从给定的 JD 和能力名称中选择已有对象；不明确时返回 CHAT。"
                ),
            },
            {"role": "user", "content": json.dumps({"message": message, "context": context}, ensure_ascii=False)},
        ],
    }
    started = time.perf_counter()
    try:
        request = Request(
            settings.llm_base_url.rstrip("/") + "/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        with urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode())
        result = json.loads(body["choices"][0]["message"]["content"])
        tool = str(result.get("tool", "CHAT")).upper()
        if tool not in ALLOWED_TOOLS:
            tool = "CHAT"
        arguments = result.get("arguments") if isinstance(result.get("arguments"), dict) else {}
        return Stage1Intent(tool, arguments, float(result.get("confidence", 0))), "llm-tool", round((time.perf_counter() - started) * 1000), None
    except Exception as exc:
        return deterministic, "llm-error", round((time.perf_counter() - started) * 1000), str(exc)[:300]
