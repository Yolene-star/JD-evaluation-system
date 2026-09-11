from collections import OrderedDict
import re


class ImmutableModelError(RuntimeError):
    pass


def _compact(name: str) -> str:
    return re.sub(r"(能力|技能|经验)$", "", name.strip().lower())


def detect_conflicts(items: list[dict]) -> list[dict]:
    original = sorted({item["name"].strip() for item in items})
    conflicts = []
    for index, left_name in enumerate(original):
        for right_name in original[index + 1:]:
            left, right = _compact(left_name), _compact(right_name)
            if ((left == right and left_name != right_name) or (left != right and (left in right or right in left))) and min(len(left), len(right)) >= 3:
                conflicts.append({"type": "SIMILAR_NAME", "names": [left_name, right_name], "blocking": True})
    return conflicts


def aggregate_competencies(items: list[dict]) -> list[dict]:
    total_jds = max(1, len({item["jd_id"] for item in items}))
    grouped: OrderedDict[str, dict] = OrderedDict()
    for item in items:
        row = grouped.setdefault(item["name"], {"name": item["name"], "description": item.get("description", ""), "source_jd_ids": [], "evidence_ids": [], "indicators": [], "evidence_requirements": [], "weight": 0.0})
        if item["jd_id"] not in row["source_jd_ids"]:
            row["source_jd_ids"].append(item["jd_id"])
        for evidence_id in item.get("evidence_ids", []):
            if evidence_id not in row["evidence_ids"]:
                row["evidence_ids"].append(evidence_id)
        for field in ("indicators", "evidence_requirements"):
            for value in item.get(field, []) or []:
                value = str(value).strip()
                if value and value not in row[field]:
                    row[field].append(value)
        row["weight"] += float(item.get("weight") or 1.0)
    total = sum(row["weight"] for row in grouped.values())
    for row in grouped.values():
        row["weight"] = row["weight"] / total if total else 0.0
        row["jd_relevance"] = len(row["source_jd_ids"]) / total_jds
        row["importance_weight"] = row["weight"]
        row["evidence_coverage"] = {"evidence_count": len(row["evidence_ids"]), "jd_count": len(row["source_jd_ids"])}
        row["source_consistency"] = len(row["source_jd_ids"]) / total_jds
    return list(grouped.values())


def confirm_model(model: dict) -> dict:
    return {**model, "status": "CONFIRMED"}


def update_competency(model: dict, **changes: str) -> dict:
    if model.get("status") == "CONFIRMED":
        raise ImmutableModelError("confirmed model is immutable")
    return {**model, **changes}
