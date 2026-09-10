from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Project, ResumeContextStatus
from ..services.resume_context import (
    cancel_current_resume,
    create_resume_version,
    get_current_resume_context,
    serialize_resume_context,
)
from ..services.resume_parser import MAX_RESUME_BYTES

router = APIRouter(tags=["resume-contexts"])


def _project_or_404(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


@router.post("/api/projects/{project_id}/resume-context")
async def upload_resume_context(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    project = _project_or_404(db, project_id)
    content = await file.read(MAX_RESUME_BYTES + 1)
    if len(content) > MAX_RESUME_BYTES:
        raise HTTPException(status_code=413, detail="RESUME_TOO_LARGE")

    resume_context = create_resume_version(
        db,
        project,
        filename=file.filename or "未命名简历",
        media_type=file.content_type or "",
        content=content,
    )
    db.commit()
    if resume_context.status is ResumeContextStatus.FAILED:
        http_status = 415 if resume_context.failure_reason == "RESUME_UNSUPPORTED_TYPE" else 422
        raise HTTPException(status_code=http_status, detail=resume_context.failure_reason)
    db.refresh(resume_context)
    return serialize_resume_context(resume_context)


@router.get("/api/projects/{project_id}/resume-context")
def get_resume_context(project_id: str, db: Session = Depends(get_db)) -> dict:
    _project_or_404(db, project_id)
    resume_context = get_current_resume_context(db, project_id)
    if resume_context is None:
        raise HTTPException(status_code=404, detail="RESUME_CONTEXT_NOT_AVAILABLE")
    return serialize_resume_context(resume_context)


@router.delete("/api/projects/{project_id}/resume-context", status_code=status.HTTP_204_NO_CONTENT)
def delete_resume_context(project_id: str, db: Session = Depends(get_db)) -> Response:
    project = _project_or_404(db, project_id)
    cancel_current_resume(db, project)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
