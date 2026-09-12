def calculate_competency_weight(coverage: float, intensity: float, task_criticality: float, level: float) -> float:
    values = (coverage, intensity, task_criticality, level)
    if any(value < 0 for value in values):
        raise ValueError("weight factors must be non-negative")
    return sum(values) / len(values)


def normalize_weights(values: list[float]) -> list[float]:
    total = sum(max(0.0, value) for value in values)
    if total == 0:
        return [0.0 for _ in values]
    return [max(0.0, value) / total for value in values]


def apply_exact_weight(items: list, target: object, value: float) -> None:
    """Keep the requested target weight and distribute the remainder across siblings."""
    if not 0 <= value <= 1:
        raise ValueError("weight must be between 0 and 1")
    others = [item for item in items if getattr(item, "id") != getattr(target, "id")]
    if not others:
        setattr(target, "weight", 1.0)
        return
    setattr(target, "weight", value)
    remainder = 1.0 - value
    current = sum(max(0.0, float(getattr(item, "weight", 0.0) or 0.0)) for item in others)
    if current:
        for item in others:
            weight = max(0.0, float(getattr(item, "weight", 0.0) or 0.0))
            setattr(item, "weight", remainder * weight / current)
    else:
        equal = remainder / len(others)
        for item in others:
            setattr(item, "weight", equal)


def apply_exact_mapping_weight(items: list[dict], target: dict, value: float) -> None:
    if not 0 <= value <= 1:
        raise ValueError("weight must be between 0 and 1")
    others = [item for item in items if item is not target]
    if not others:
        target["weight"] = 1.0
        return
    target["weight"] = value
    remainder = 1.0 - value
    current = sum(max(0.0, float(item.get("weight") or 0.0)) for item in others)
    if current:
        for item in others:
            item["weight"] = remainder * max(0.0, float(item.get("weight") or 0.0)) / current
    else:
        equal = remainder / len(others)
        for item in others:
            item["weight"] = equal
