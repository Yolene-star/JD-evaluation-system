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
