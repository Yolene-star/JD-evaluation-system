from __future__ import annotations

import hashlib
from pathlib import PurePath

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..models import Project, ResumeContextStatus, ResumeContextVersion
from .audit import record_event
from .resume_parser import ResumeParseError, parse_resume

RESUME_PARSER_VERSION = "resume-v1"


def get_current_resume_context(db: Session, project_id: str) -> ResumeContextVersion | None:
    return db.scalar(
        select(ResumeContextVersion)
        .where(
            ResumeContextVersion.project_id == project_id,
            ResumeContextVersion.is_current.is_(True),
        )
        .order_by(ResumeContextVersion.version.desc())
    )


def create_resume_version(
    db: Session,
    project: Project,
    *,
    filename: str,
    media_type: str,
    content: bytes,
) -> ResumeContextVersion:
    """Persist a new parse attempt without disturbing the current version on failure."""
    version = (db.scalar(select(func.max(ResumeContextVersion.version)).where(ResumeContextVersion.project_id == project.id)) or 0) + 1
    source_filename = PurePath(filename).name[:255] or "未命名简历"
    content_sha256 = hashlib.sha256(content).hexdigest()
    try:
        parsed = parse_resume(source_filename, media_type, content)
    except ResumeParseError as error:
        return _record_failed_version(
            db,
            project,
            version=version,
            source_filename=source_filename,
            media_type=media_type,
            file_size=len(content),
            content_sha256=content_sha256,
            error_code=error.code,
        )
    except Exception:
        return _record_failed_version(
            db,
            project,
            version=version,
            source_filename=source_filename,
            media_type=media_type,
            file_size=len(content),
            content_sha256=content_sha256,
            error_code="RESUME_PARSE_FAILED",
        )

    resume_context = ResumeContextVersion(
        project_id=project.id,
        version=version,
        is_current=False,
        source_filename=source_filename,
        media_type=media_type,
        file_size=len(content),
        content_sha256=parsed.content_sha256,
        normalized_text=parsed.normalized_text,
        structured_context_json=parsed.context.model_dump(mode="json"),
        parser_version=RESUME_PARSER_VERSION,
        status=ResumeContextStatus.READY,
    )
    db.add(resume_context)
    db.flush()
    db.execute(
        update(ResumeContextVersion)
        .where(
            ResumeContextVersion.project_id == project.id,
            ResumeContextVersion.id != resume_context.id,
        )
        .values(is_current=False)
    )
    resume_context.is_current = True
    record_event(
        db,
        project.id,
        "RESUME_CONTEXT_READY",
        _audit_payload(resume_context),
    )
    return resume_context


def cancel_current_resume(db: Session, project: Project) -> ResumeContextVersion | None:
    resume_context = get_current_resume_context(db, project.id)
    if resume_context is None:
        return None
    resume_context.is_current = False
    record_event(
        db,
        project.id,
        "RESUME_CONTEXT_CANCELLED",
        _audit_payload(resume_context),
    )
    return resume_context


def serialize_resume_context(resume_context: ResumeContextVersion) -> dict:
    """Expose only safe summary metadata, never retained normalized resume text."""
    context = resume_context.structured_context_json or {}
    return {
        "id": resume_context.id,
        "version": resume_context.version,
        "status": resume_context.status.value,
        "source_filename": resume_context.source_filename,
        "media_type": resume_context.media_type,
        "file_size": resume_context.file_size,
        "content_sha256": resume_context.content_sha256,
        "parser_version": resume_context.parser_version,
        "source_type": context.get("source_type", "BACKGROUND_ONLY"),
        "education": context.get("education", []),
        "projects": context.get("projects", []),
        "skills": context.get("skills", []),
        "experiences": context.get("experiences", []),
        "summary": context.get("summary", ""),
    }


def _record_failed_version(
    db: Session,
    project: Project,
    *,
    version: int,
    source_filename: str,
    media_type: str,
    file_size: int,
    content_sha256: str,
    error_code: str,
) -> ResumeContextVersion:
    resume_context = ResumeContextVersion(
        project_id=project.id,
        version=version,
        is_current=False,
        source_filename=source_filename,
        media_type=media_type,
        file_size=file_size,
        content_sha256=content_sha256,
        normalized_text="",
        structured_context_json={},
        parser_version=RESUME_PARSER_VERSION,
        status=ResumeContextStatus.FAILED,
        failure_reason=error_code,
    )
    db.add(resume_context)
    db.flush()
    record_event(
        db,
        project.id,
        "RESUME_CONTEXT_FAILED",
        _audit_payload(resume_context, error_code=error_code),
    )
    return resume_context


def _audit_payload(resume_context: ResumeContextVersion, *, error_code: str | None = None) -> dict:
    payload = {
        "resume_context_version_id": resume_context.id,
        "content_sha256": resume_context.content_sha256,
        "status": resume_context.status.value,
        "parser_version": resume_context.parser_version,
    }
    if error_code is not None:
        payload["error_code"] = error_code
    return payload
