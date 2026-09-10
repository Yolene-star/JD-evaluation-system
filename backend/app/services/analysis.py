from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import Competency, Evidence, JobDescription, JobDescriptionStatus, Project, ProjectStatus
from .audit import record_event
from .parsing import parse_jd


def analyze_project_jds(db: Session, project: Project, *, jd_ids: set[str] | None = None) -> list[str]:
    """Deterministically rebuild participating JD competencies and evidence."""
    project.status = ProjectStatus.ANALYZING
    query = select(JobDescription).where(
        JobDescription.project_id == project.id,
        JobDescription.participates_in_model.is_(True),
    )
    if jd_ids is not None:
        query = query.where(JobDescription.id.in_(jd_ids))
    jobs = db.scalars(query).all()
    analyzed_ids: list[str] = []
    for jd in jobs:
        jd.status = JobDescriptionStatus.PROCESSING
        db.execute(delete(Competency).where(Competency.jd_id == jd.id))
        db.execute(delete(Evidence).where(Evidence.jd_id == jd.id))
        parsed = parse_jd(jd.raw_text)
        for item in parsed.competencies:
            evidence = Evidence(
                jd_id=jd.id,
                excerpt=item.excerpt,
                start_offset=item.start_offset,
                end_offset=item.end_offset,
            )
            db.add(evidence)
            db.flush()
            db.add(Competency(jd_id=jd.id, name=item.name, evidence_ids=[evidence.id]))
        jd.status = JobDescriptionStatus.COMPLETED
        analyzed_ids.append(jd.id)
    project.status = ProjectStatus.REVIEWING
    record_event(db, project.id, "ANALYSIS_COMPLETED", {"job_ids": analyzed_ids})
    return analyzed_ids
