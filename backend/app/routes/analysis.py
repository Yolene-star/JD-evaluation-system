from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Competency, Evidence, JobDescription, Project
from ..services.analysis import analyze_project_jds
from ..services.parsing import parse_jd
from ..services.weights import normalize_weights

router = APIRouter(prefix="/api/projects", tags=["analysis"])


def get_project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


@router.post("/{project_id}/analysis/run")
def run_analysis(project_id: str, db: Session = Depends(get_db)) -> dict:
    project = get_project(db, project_id)
    job_ids = analyze_project_jds(db, project)
    db.commit()
    return {"project_status": project.status, "job_ids": job_ids}


@router.get("/{project_id}/analysis")
def get_analysis(project_id: str, db: Session = Depends(get_db)) -> dict:
    project = get_project(db, project_id)
    jds = db.scalars(select(JobDescription).where(JobDescription.project_id == project_id).order_by(JobDescription.created_at)).all()
    result = []
    for jd in jds:
        competencies = db.scalars(select(Competency).where(Competency.jd_id == jd.id)).all()
        evidence = db.scalars(select(Evidence).where(Evidence.jd_id == jd.id)).all()
        parsed = parse_jd(jd.raw_text)
        result.append({"id": jd.id, "title": jd.title, "status": jd.status, "participates_in_model": jd.participates_in_model, "raw_text": jd.raw_text, "requirements": list(parsed.qualifications + parsed.constraints), "competencies": [{"id": c.id, "name": c.name, "description": c.description, "evidence_ids": c.evidence_ids, "weight": c.weight} for c in competencies], "evidence": [{"id": e.id, "excerpt": e.excerpt, "start_offset": e.start_offset, "end_offset": e.end_offset} for e in evidence]})
    return {"project_status": project.status, "jds": result, "warnings": []}
