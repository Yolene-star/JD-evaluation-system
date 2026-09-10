from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urlparse


@dataclass(frozen=True)
class JdAdapter:
    name: str
    title_selectors: tuple[str, ...]
    content_selectors: tuple[str, ...]


@dataclass(frozen=True)
class ExtractionResult:
    adapter: str
    title: str
    text: str
    fields: dict[str, str] = field(default_factory=dict)


ADAPTERS = {
    "boss-zhipin": JdAdapter(
        "boss-zhipin",
        ("job-name", "job-title", "name"),
        ("job-detail", "job-detail-content", "job-sec-text", "job-primary"),
    ),
    "mokahr": JdAdapter(
        "mokahr",
        ("job-detail-title", "position-name", "job-title", "h1"),
        ("job-detail", "position-detail", "position-content", "job-description"),
    ),
    "universal": JdAdapter(
        "universal",
        ("job-title", "position-title", "title", "h1", "title"),
        ("job-detail", "position-detail", "jd-content", "job-content", "job-description", "main", "article"),
    ),
}


class _Node:
    def __init__(self, tag: str = "root", attrs: dict[str, str] | None = None) -> None:
        self.tag = tag
        self.attrs = attrs or {}
        self.children: list[_Node | str] = []

    @property
    def classes(self) -> set[str]:
        return set(self.attrs.get("class", "").split())

    def text(self) -> str:
        parts: list[str] = []
        for child in self.children:
            parts.append(child if isinstance(child, str) else child.text())
        return " ".join(" ".join(parts).split())


class _TreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node()
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(tag, {key: value or "" for key, value in attrs})
        self.stack[-1].children.append(node)
        if tag not in {"meta", "link", "img", "br", "input", "hr"}:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.stack[-1].children.append(data.strip())


def select_adapter(url: str) -> JdAdapter:
    parsed = urlparse(url)
    host = parsed.netloc.lower().split(":", 1)[0]
    path = parsed.path.lower()
    if host == "zhipin.com" or host.endswith(".zhipin.com"):
        return ADAPTERS["boss-zhipin"]
    if "mokahr" in host or "mokahr" in path:
        return ADAPTERS["mokahr"]
    return ADAPTERS["universal"]


def _walk(node: _Node) -> list[_Node]:
    result = [node]
    for child in node.children:
        if isinstance(child, _Node):
            result.extend(_walk(child))
    return result


def _excluded(node: _Node) -> bool:
    marker = " ".join([node.attrs.get("id", ""), node.attrs.get("class", "")]).lower()
    return any(term in marker for term in ("recommend", "related", "similar", "sider", "sidebar", "other-job"))


def _matching_text(nodes: list[_Node], selector: str) -> str:
    for node in nodes:
        if _excluded(node):
            continue
        if selector.startswith(".") and selector[1:] in node.classes:
            text = node.text()
        elif selector.startswith("#") and selector[1:] == node.attrs.get("id"):
            text = node.text()
        elif selector in {"h1", "h2", "main", "article"} and node.tag == selector:
            text = node.text()
        elif selector == "title" and node.tag == "title":
            text = node.text()
        else:
            continue
        if text:
            return text
    return ""


def _best_content(nodes: list[_Node], adapter: JdAdapter) -> str:
    candidates = []
    for selector in adapter.content_selectors:
        for node in nodes:
            if _excluded(node):
                continue
            matches = (selector.startswith(".") and selector[1:] in node.classes) or (selector in {"main", "article"} and node.tag == selector)
            if matches:
                text = node.text()
                if text:
                    candidates.append(text)
    if candidates:
        return max(candidates, key=len)
    return max((node.text() for node in nodes if not _excluded(node)), key=len, default="")


def extract_html(url: str, html: str) -> ExtractionResult:
    adapter = select_adapter(url)
    parser = _TreeParser()
    parser.feed(html)
    nodes = _walk(parser.root)
    title = ""
    for selector in adapter.title_selectors:
        title = _matching_text(nodes, selector)
        if title:
            break
    text = _best_content(nodes, adapter)
    fields: dict[str, str] = {}
    if adapter.name == "mokahr":
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if "职位描述" in lines:
            start = lines.index("职位描述") + 1
            end = lines.index("职位信息", start) if "职位信息" in lines[start:] else len(lines)
            text = "\n".join(lines[start:end]).strip() or text
        for label in ("职位名称", "工作地点", "薪资范围", "所属部门"):
            if label in lines:
                index = lines.index(label) + 1
                while index < len(lines) and lines[index] == label:
                    index += 1
                if index < len(lines):
                    fields[label] = lines[index]
        title = fields.get("职位名称") or title
    return ExtractionResult(adapter=adapter.name, title=title.strip() or "网页岗位", text=text.strip(), fields=fields)
