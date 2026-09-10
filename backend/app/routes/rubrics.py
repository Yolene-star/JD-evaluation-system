from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ModelVersion, RubricSet
from ..services.rubrics import activate_rubric_set, create_default_rubric_set

router = APIRouter(tags=["rubrics"])


def _payload(rubric: RubricSet) -> dict:
    return {"id": rubric.id, "model_version_id": rubric.model_version_id, "version": rubric.version, "status": rubric.status.value, "scoring_rule_version": rubric.scoring_rule_version, "competencies": [{"competency_id": item.competency_id, "indicators": item.indicators, "scoring_rules": item.scoring_rules} for item in rubric.competencies]}


@router.get("/api/model-versions/{model_version_id}/rubrics")
def list_rubrics(model_version_id: str, db: Session = Depends(get_db)) -> list[dict]:
    if db.get(ModelVersion, model_version_id) is None:
        raise HTTPException(status_code=404, detail="模型版本不存在")
    return [_payload(item) for item in db.scalars(select(RubricSet).where(RubricSet.model_version_id == model_version_id).order_by(RubricSet.created_at.desc())).all()]


@router.post("/api/model-versions/{model_version_id}/rubrics")
def create_rubric(model_version_id: str, payload: dict, db: Session = Depends(get_db)) -> dict:
    try:
        rubric = create_default_rubric_set(db, model_version_id, payload.get("competencies", []), str(payload.get("version", "r1")))
        db.commit()
        return _payload(rubric)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/api/rubric-sets/{rubric_set_id}")
def get_rubric(rubric_set_id: str, db: Session = Depends(get_db)) -> dict:
    rubric = db.get(RubricSet, rubric_set_id)
    if rubric is None:
        raise HTTPException(status_code=404, detail="Rubric 不存在")
    return _payload(rubric)


@router.post("/api/rubric-sets/{rubric_set_id}/activate")
def activate(rubric_set_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        rubric = activate_rubric_set(db, rubric_set_id)
        db.commit()
        return _payload(rubric)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
