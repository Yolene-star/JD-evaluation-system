from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Command:
    action: str
    target: str | None = None
    value: float | None = None
    text: str | None = None
    requires_confirmation: bool = False


def extract_pasted_jd(message: str) -> Command | None:
    explicit = re.match(r"\s*(?:保存|导入|添加)(?:这份|该)?\s*JD\s*[:：]?\s*(.*)", message, re.IGNORECASE | re.DOTALL)
    markers = ("岗位职责", "任职要求", "职位描述", "工作内容", "岗位要求", "负责")
    marker_count = sum(marker in message for marker in markers)
    if not explicit and (len(message) < 50 or marker_count < 1):
        return None
    text = (explicit.group(1) if explicit else message).strip()
    if len(text) < 30:
        return None
    title_match = re.search(r"(?:岗位名称|职位名称|职位)\s*[:：]\s*([^\n]+)", text)
    title = title_match.group(1).strip() if title_match else None
    return Command("INGEST_JD", target=title, text=text, requires_confirmation=not explicit and marker_count < 2)


def parse_command(message: str) -> Command:
    match = re.search(r"(?:移除|删除|排除).*?[《「\"]([^》」\"]+)[》」\"]", message)
    if match:
        return Command("REMOVE_JD", target=match.group(1).strip())
    weight = re.search(r"(?:提高|设置|调整).*?权重.*?(\d+(?:\.\d+)?)\s*%", message)
    if weight:
        return Command("EDIT_WEIGHT", value=float(weight.group(1)))
    return Command("CHAT")
