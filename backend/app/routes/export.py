from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ModelSnapshot

router = APIRouter(tags=["export"])


@router.get("/api/models/{model_id}/export")
def export_model(model_id: str, db: Session = Depends(get_db)) -> dict:
    snapshot = db.scalar(select(ModelSnapshot).where(ModelSnapshot.model_version_id == model_id))
    if not snapshot:
        raise HTTPException(status_code=409, detail="模型尚未确认")
    return {**snapshot.snapshot_json, "version": snapshot.version, "created_at": snapshot.created_at}
