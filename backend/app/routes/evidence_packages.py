from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..services.evidence_package import EvidencePackageNotReady, build_evidence_package

router = APIRouter(tags=["evidence-packages"])


@router.get("/api/assessments/{session_id}/evidence-package")
def evidence_package(session_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        return build_evidence_package(db, session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except EvidencePackageNotReady as exc:
        raise HTTPException(status_code=409, detail=str(exc))
