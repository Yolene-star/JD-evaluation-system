from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CompetencyRubric, ModelVersion, RubricSet, RubricSetStatus


def create_default_rubric_set(db: Session, model_version_id: str, competencies: list[dict], version: str = "r1") -> RubricSet:
    if db.get(ModelVersion, model_version_id) is None:
        raise KeyError("model version not found")
    if not competencies:
        raise ValueError("rubric requires at least one competency")
    ids = [str(item.get("id") or item.get("competency_id")) for item in competencies]
    if any(not item or item == "None" for item in ids) or len(set(ids)) != len(ids):
        raise ValueError("competency ids must be unique")
    total = sum(float(item.get("weight", 0)) for item in competencies)
    if total <= 0:
        raise ValueError("competency weights must sum to a positive value")
    rubric = RubricSet(model_version_id=model_version_id, version=version, status=RubricSetStatus.DRAFT, scoring_rule_version="stage3-v1")
    db.add(rubric)
    db.flush()
    for item, competency_id in zip(competencies, ids):
        indicators = item.get("indicators") or [str(item.get("name", competency_id))]
        db.add(CompetencyRubric(rubric_set_id=rubric.id, competency_id=competency_id, rubric_version="stage3-v1", indicators=indicators, scoring_rules={"weight": float(item.get("weight", 0))}))
    db.flush()
    return rubric


def activate_rubric_set(db: Session, rubric_set_id: str) -> RubricSet:
    rubric = db.get(RubricSet, rubric_set_id)
    if rubric is None:
        raise KeyError("rubric set not found")
    if rubric.status is RubricSetStatus.ACTIVE:
        return rubric
    if not rubric.competencies:
        raise ValueError("rubric set has no competencies")
    existing = db.scalars(select(RubricSet).where(RubricSet.model_version_id == rubric.model_version_id, RubricSet.status == RubricSetStatus.ACTIVE)).all()
    for old in existing:
        old.status = RubricSetStatus.RETIRED
    rubric.status = RubricSetStatus.ACTIVE
    rubric.activated_at = datetime.now(timezone.utc)
    db.flush()
    return rubric


def get_active_rubric_set(db: Session, model_version_id: str) -> RubricSet | None:
    return db.scalar(select(RubricSet).where(RubricSet.model_version_id == model_version_id, RubricSet.status == RubricSetStatus.ACTIVE).order_by(RubricSet.created_at.desc()))
