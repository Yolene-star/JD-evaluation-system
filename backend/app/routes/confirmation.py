from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Competency, JobDescription, ModelSnapshot, ModelVersion, ModelVersionStatus, ConflictDecisionRecord
from ..services.aggregation import aggregate_competencies, detect_conflicts
from ..services.audit import record_event

router = APIRouter(tags=["confirmation"])


def snapshot_payload(model_id: str, db: Session) -> dict:
    model = db.get(ModelVersion, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")
    draft = model.draft_json or {}
    if draft.get("competencies") is not None and draft.get("manual_overrides"):
        return {"model_id": model.id, "project_id": model.project_id, "competencies": draft.get("competencies", []), "conflict_count": len(draft.get("conflicts", []))}
    jds = db.scalars(select(JobDescription).where(JobDescription.project_id == model.project_id, JobDescription.participates_in_model.is_(True))).all()
    items = [{"name": c.name, "jd_id": jd.id, "evidence_ids": c.evidence_ids} for jd in jds for c in db.scalars(select(Competency).where(Competency.jd_id == jd.id)).all()]
    return {"model_id": model.id, "project_id": model.project_id, "competencies": aggregate_competencies(items), "conflict_count": 0}


@router.post("/api/models/{model_id}/confirm", status_code=201)
def confirm_model(model_id: str, db: Session = Depends(get_db)) -> dict:
    model = db.get(ModelVersion, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")
    if model.status == ModelVersionStatus.CONFIRMED or db.scalar(select(ModelSnapshot).where(ModelSnapshot.model_version_id == model_id)):
        raise HTTPException(status_code=409, detail="模型已经确认并冻结")
    payload = snapshot_payload(model_id, db)
    conflicts = detect_conflicts([{**item, "jd_id": source_id} for item in payload["competencies"] for source_id in item["source_jd_ids"]])
    resolved = {row.conflict_key for row in db.scalars(select(ConflictDecisionRecord).where(ConflictDecisionRecord.model_version_id == model_id)).all()}
    conflicts = [row for row in conflicts if "|".join(sorted(row["names"])) not in resolved]
    if conflicts:
        raise HTTPException(status_code=409, detail={"code": "BLOCKING_CONFLICTS", "conflicts": conflicts})
    model.status = ModelVersionStatus.CONFIRMED
    model.version = "v1.0"
    db.add(ModelSnapshot(model_version_id=model.id, version="v1.0", snapshot_json=payload))
    record_event(db, model.project_id, "MODEL_CONFIRMED", {"model_id": model.id, "version": "v1.0"})
    db.commit()
    return {"id": model.id, "version": "v1.0", "status": "CONFIRMED", "competencies": payload["competencies"]}
