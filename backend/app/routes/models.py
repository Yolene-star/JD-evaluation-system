from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Competency, JobDescription, ModelVersion, ModelVersionStatus, Project, ModelSnapshot, ConflictDecisionRecord
from ..services.aggregation import aggregate_competencies, detect_conflicts
from ..services.audit import record_event
from ..services.weights import apply_exact_weight

router = APIRouter(tags=["models"])


def ensure_editable(jd: JobDescription, db: Session) -> None:
    if db.scalar(select(ModelSnapshot).join(ModelVersion, ModelSnapshot.model_version_id == ModelVersion.id).where(ModelVersion.project_id == jd.project_id)):
        raise HTTPException(status_code=409, detail="已确认模型不可修改，请创建新版本")


@router.post("/api/jds/{jd_id}/competencies", status_code=201)
def create_competency(jd_id: str, payload: dict, db: Session = Depends(get_db)) -> dict:
    jd = db.get(JobDescription, jd_id)
    if not jd: raise HTTPException(status_code=404, detail="JD不存在")
    ensure_editable(jd, db)
    name = str(payload.get("name", "")).strip()
    if not name: raise HTTPException(status_code=422, detail="能力名称不能为空")
    competency = Competency(jd_id=jd.id, name=name, evidence_ids=[])
    db.add(competency); record_event(db, jd.project_id, "COMPETENCY_CREATED", {"competency_id": competency.id, "name": name}); db.commit(); db.refresh(competency)
    return {"id": competency.id, "jd_id": jd.id, "name": competency.name, "evidence_ids": competency.evidence_ids}


@router.delete("/api/competencies/{competency_id}", status_code=204)
def delete_competency(competency_id: str, db: Session = Depends(get_db)) -> None:
    competency = db.get(Competency, competency_id)
    if not competency: raise HTTPException(status_code=404, detail="能力项不存在")
    jd = db.get(JobDescription, competency.jd_id); ensure_editable(jd, db)
    record_event(db, jd.project_id, "COMPETENCY_DELETED", {"competency_id": competency.id, "name": competency.name})
    db.delete(competency); db.commit()

def unresolved(model_id: str, conflicts: list[dict], db: Session) -> list[dict]:
    keys = {row.conflict_key for row in db.scalars(select(ConflictDecisionRecord).where(ConflictDecisionRecord.model_version_id == model_id)).all()}
    return [row for row in conflicts if "|".join(sorted(row["names"])) not in keys]


@router.patch("/api/competencies/{competency_id}")
def update_competency(competency_id: str, payload: dict, db: Session = Depends(get_db)) -> dict:
    competency = db.get(Competency, competency_id)
    if not competency:
        raise HTTPException(status_code=404, detail="能力项不存在")
    jd = db.get(JobDescription, competency.jd_id)
    ensure_editable(jd, db)
    name = str(payload.get("name", "")).strip()
    if "name" in payload and not name:
        raise HTTPException(status_code=422, detail="能力名称不能为空")
    if name:
        competency.name = name
    if "weight" in payload:
        try:
            weight = float(payload["weight"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="权重必须是数字")
        if not 0 <= weight <= 1:
            raise HTTPException(status_code=422, detail="权重必须在 0 到 1 之间")
        siblings = db.scalars(select(Competency).where(Competency.jd_id == jd.id)).all()
        apply_exact_weight(siblings, competency, weight)
    record_event(db, jd.project_id, "COMPETENCY_UPDATED", {"competency_id": competency.id, "name": competency.name, "weight": competency.weight})
    db.commit()
    db.refresh(competency)
    return {"id": competency.id, "name": competency.name, "impact_preview": {"weight_recalculation": True}}


@router.post("/api/models/{model_id}/conflicts/{conflict_id}/resolve")
def resolve_conflict(model_id: str, conflict_id: str, payload: dict, db: Session = Depends(get_db)) -> dict:
    model = db.get(ModelVersion, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")
    decision = payload.get("decision")
    if decision not in {"MERGE", "SEPARATE", "RENAME_MERGE"}:
        raise HTTPException(status_code=422, detail="无效的冲突决策")
    jds = db.scalars(select(JobDescription).where(JobDescription.project_id == model.project_id, JobDescription.participates_in_model.is_(True))).all()
    items = [{"name": c.name, "jd_id": jd.id, "evidence_ids": c.evidence_ids, "weight": c.weight} for jd in jds for c in db.scalars(select(Competency).where(Competency.jd_id == jd.id)).all()]
    conflicts = unresolved(model.id, detect_conflicts(items), db)
    try:
        conflict = conflicts[int(conflict_id)]
    except (ValueError, IndexError):
        raise HTTPException(status_code=404, detail="冲突不存在")
    db.add(ConflictDecisionRecord(model_version_id=model.id, conflict_key="|".join(sorted(conflict["names"])), decision=decision))
    record_event(db, model.project_id, "CONFLICT_RESOLVED", {"model_id": model.id, "decision": decision, "conflict": conflict["names"]})
    db.commit()
    return {"conflict_id": conflict_id, "decision": decision, "status": "RESOLVED"}


@router.post("/api/projects/{project_id}/aggregate")
def aggregate_model(project_id: str, db: Session = Depends(get_db)) -> dict:
    if not db.get(Project, project_id):
        raise HTTPException(status_code=404, detail="项目不存在")
    jds = db.scalars(select(JobDescription).where(JobDescription.project_id == project_id, JobDescription.participates_in_model.is_(True))).all()
    items = [item for jd in jds for item in [{"name": c.name, "jd_id": jd.id, "evidence_ids": c.evidence_ids, "weight": c.weight} for c in db.scalars(select(Competency).where(Competency.jd_id == jd.id)).all()]]
    rows = aggregate_competencies(items)
    conflicts = detect_conflicts(items)
    model = ModelVersion(project_id=project_id, version="draft", status=ModelVersionStatus.DRAFT, draft_json={"competencies": rows, "conflicts": conflicts, "manual_overrides": False})
    db.add(model)
    db.flush()
    record_event(db, project_id, "MODEL_AGGREGATED", {"model_id": model.id, "competency_count": len(rows)})
    db.commit()
    conflicts = unresolved(model.id, conflicts, db)
    return {"id": model.id, "project_id": project_id, "version": model.version, "status": model.status, "competencies": rows, "conflict_count": len(conflicts), "conflicts": conflicts}


@router.get("/api/models/{model_id}")
def get_model(model_id: str, db: Session = Depends(get_db)) -> dict:
    model = db.get(ModelVersion, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")
    draft = model.draft_json or {}
    if draft.get("competencies") is not None and (draft.get("manual_overrides") or model.status == ModelVersionStatus.CONFIRMED):
        conflicts = unresolved(model.id, draft.get("conflicts", []), db)
        return {"id": model.id, "project_id": model.project_id, "version": model.version, "status": model.status, "competencies": draft.get("competencies", []), "conflict_count": len(conflicts), "conflicts": conflicts}
    jds = db.scalars(select(JobDescription).where(JobDescription.project_id == model.project_id, JobDescription.participates_in_model.is_(True))).all()
    items = [item for jd in jds for item in [{"name": c.name, "jd_id": jd.id, "evidence_ids": c.evidence_ids, "weight": c.weight} for c in db.scalars(select(Competency).where(Competency.jd_id == jd.id)).all()]]
    conflicts = unresolved(model.id, detect_conflicts(items), db)
    return {"id": model.id, "project_id": model.project_id, "version": model.version, "status": model.status, "competencies": aggregate_competencies(items), "conflict_count": len(conflicts), "conflicts": conflicts}


@router.get("/api/projects/{project_id}/models/latest")
def get_latest_model(project_id: str, db: Session = Depends(get_db)) -> dict:
    model = db.scalar(select(ModelVersion).where(ModelVersion.project_id == project_id).order_by(ModelVersion.created_at.desc()))
    if not model:
        raise HTTPException(status_code=404, detail="项目尚未生成模型")
    return get_model(model.id, db)
