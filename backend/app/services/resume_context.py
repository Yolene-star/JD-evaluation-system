from __future__ import annotations

import hashlib

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Project, ResumeContextStatus, ResumeContextVersion
from .audit import record_event
from .resume_parser import ResumeParseError, parse_resume

RESUME_PARSER_VERSION = "resume-v1"
MAX_VERSION_ALLOCATION_ATTEMPTS = 3


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
    source_filename = _display_filename(filename)
    content_sha256 = hashlib.sha256(content).hexdigest()
    try:
        parsed = parse_resume(source_filename, media_type, content)
    except ResumeParseError as error:
        return _persist_resume_attempt(
            db, project,
            lambda version: _failed_resume_context(
                project, version, source_filename, media_type, len(content), content_sha256, error.code
            ),
        )
    except Exception:
        return _persist_resume_attempt(
            db, project,
            lambda version: _failed_resume_context(
                project, version, source_filename, media_type, len(content), content_sha256, "RESUME_PARSE_FAILED"
            ),
        )

    return _persist_resume_attempt(
        db, project,
        lambda version: ResumeContextVersion(
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
        ),
    )


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


def _persist_resume_attempt(
    db: Session,
    project: Project,
    build_resume_context,
) -> ResumeContextVersion:
    for attempt in range(MAX_VERSION_ALLOCATION_ATTEMPTS):
        try:
            with db.begin_nested():
                version = (db.scalar(select(func.max(ResumeContextVersion.version)).where(ResumeContextVersion.project_id == project.id)) or 0) + 1
                resume_context = build_resume_context(version)
                db.add(resume_context)
                db.flush()
                if resume_context.status is ResumeContextStatus.READY:
                    db.execute(
                        update(ResumeContextVersion)
                        .where(
                            ResumeContextVersion.project_id == project.id,
                            ResumeContextVersion.id != resume_context.id,
                        )
                        .values(is_current=False)
                    )
                    resume_context.is_current = True
                    action = "RESUME_CONTEXT_READY"
                else:
                    action = "RESUME_CONTEXT_FAILED"
                record_event(
                    db,
                    project.id,
                    action,
                    _audit_payload(resume_context, error_code=resume_context.failure_reason),
                )
            return resume_context
        except IntegrityError:
            if attempt == MAX_VERSION_ALLOCATION_ATTEMPTS - 1:
                raise
    raise RuntimeError("resume version allocation retry exhausted")


def _failed_resume_context(
    project: Project,
    version: int,
    source_filename: str,
    media_type: str,
    file_size: int,
    content_sha256: str,
    error_code: str,
) -> ResumeContextVersion:
    return ResumeContextVersion(
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


def _display_filename(filename: str) -> str:
    return filename.replace("\\", "/").rsplit("/", 1)[-1][:255] or "未命名简历"


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
