from dataclasses import dataclass
from uuid import uuid4


@dataclass(frozen=True)
class ParsedCompetency:
    name: str
    evidence_ids: tuple[str, ...]
    excerpt: str
    start_offset: int
    end_offset: int


@dataclass(frozen=True)
class ParsedJd:
    competencies: tuple[ParsedCompetency, ...]
    qualifications: tuple[str, ...]
    constraints: tuple[str, ...]


LEXICON = (("React", "组件化开发"), ("组件开发", "组件化开发"), ("页面性能", "性能优化"), ("性能", "性能优化"), ("数据分析能力", "数据分析能力"), ("数据分析", "数据分析"), ("需求分析", "需求分析"), ("跨团队协作", "跨团队协作"))


def parse_jd(text: str) -> ParsedJd:
    found: dict[str, ParsedCompetency] = {}
    for keyword, name in LEXICON:
        start = text.find(keyword)
        if start < 0 or name in found:
            continue
        end = start + len(keyword)
        found[name] = ParsedCompetency(name, (str(uuid4()),), text[start:end], start, end)
    qualifications = tuple(x for x in ("本科", "硕士", "学士") if x in text)
    constraints = tuple(x for x in ("北京", "上海", "远程") if x in text)
    return ParsedJd(tuple(found.values()), qualifications, constraints)
