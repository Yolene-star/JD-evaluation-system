from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import is_llm_analysis_enabled, settings
from ..models import Competency, Evidence, JobDescription, JobDescriptionStatus, LLMCallLog, Project, ProjectStatus
from .ai_parsing import PROMPT_VERSION, parse_jd_with_llm
from .audit import record_event
from .parsing import parse_jd


def analyze_project_jds(db: Session, project: Project, *, jd_ids: set[str] | None = None) -> list[str]:
    """Rebuild participating JD competencies from validated, traceable parser output."""
    project.status = ProjectStatus.ANALYZING
    query = select(JobDescription).where(
        JobDescription.project_id == project.id,
        JobDescription.participates_in_model.is_(True),
    )
    if jd_ids is not None:
        query = query.where(JobDescription.id.in_(jd_ids))
    jobs = db.scalars(query).all()
    analyzed_ids: list[str] = []
    parser_sources: dict[str, str] = {}
    for jd in jobs:
        jd.status = JobDescriptionStatus.PROCESSING
        if is_llm_analysis_enabled():
            parsed, source, latency, error = parse_jd_with_llm(jd.raw_text)
        else:
            parsed, source, latency, error = parse_jd(jd.raw_text), "deterministic", None, None
        db.add(LLMCallLog(
            project_id=project.id,
            task_type="stage1-jd-analysis",
            model=settings.llm_model if source == "llm" else "deterministic-parser",
            prompt_version=PROMPT_VERSION,
            status=source,
            latency_ms=latency,
            error=error,
        ))
        parser_sources[jd.id] = source
        if not parsed.competencies:
            jd.status = JobDescriptionStatus.FAILED
            record_event(db, project.id, "ANALYSIS_FAILED", {
                "job_id": jd.id,
                "parser_source": source,
                "reason": error or "未识别到具有原文证据的能力项",
            })
            continue
        # Only replace the previous model after a complete parser result exists.
        db.execute(delete(Competency).where(Competency.jd_id == jd.id))
        db.execute(delete(Evidence).where(Evidence.jd_id == jd.id))
        for item in parsed.competencies:
            evidence = Evidence(
                jd_id=jd.id,
                excerpt=item.excerpt,
                start_offset=item.start_offset,
                end_offset=item.end_offset,
            )
            db.add(evidence)
            db.flush()
            db.add(Competency(
                jd_id=jd.id,
                name=item.name,
                description=item.description,
                evidence_ids=[evidence.id],
            ))
        jd.status = JobDescriptionStatus.COMPLETED
        analyzed_ids.append(jd.id)
    project.status = ProjectStatus.REVIEWING
    record_event(db, project.id, "ANALYSIS_COMPLETED", {
        "job_ids": analyzed_ids,
        "parser_sources": parser_sources,
    })
    return analyzed_ids
