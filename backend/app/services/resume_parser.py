from __future__ import annotations

import hashlib
import re
from io import BytesIO
from pathlib import PurePath
from zipfile import BadZipFile

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError, PdfReadError

from .resume_schemas import CandidateBackground, ParsedResumeContext, ResumeBackgroundItem, ResumeSourceSegment

MAX_RESUME_BYTES = 5 * 1024 * 1024
SUPPORTED_RESUME_TYPES = {
    ".txt": "text/plain",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

_EMAIL_PATTERN = re.compile(r"(?i)[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}")
_PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")
_ADDRESS_LINE_PATTERN = re.compile(r"(?:地址|住址|居住地|联系地址|address)\s*[:：]", re.IGNORECASE)
_CONTROL_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE_PATTERN = re.compile(r"[ \t\r\f\v]+")
_HEADING_BUCKETS = (
    (re.compile(r"^(?:教育(?:经历|背景)?|学历|education)[:：]?$", re.IGNORECASE), "education"),
    (re.compile(r"^(?:项目(?:经历)?|项目经验|projects?)[:：]?$", re.IGNORECASE), "projects"),
    (re.compile(r"^(?:技能|专业技能|skills?)[:：]?$", re.IGNORECASE), "skills"),
    (re.compile(r"^(?:工作经历|工作经验|实习经历|职业经历|experience)[:：]?$", re.IGNORECASE), "experiences"),
)
_INLINE_BUCKETS = (
    (re.compile(r"^(?:项目|project)\s*[:：]", re.IGNORECASE), "projects"),
    (re.compile(r"^(?:技能|专业技能|skills?)\s*[:：]", re.IGNORECASE), "skills"),
    (re.compile(r"^(?:教育|学历|education)\s*[:：]", re.IGNORECASE), "education"),
    (re.compile(r"^(?:工作|实习|experience)\s*[:：]", re.IGNORECASE), "experiences"),
)


class ResumeParseError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def parse_resume(filename: str, media_type: str, content: bytes) -> ParsedResumeContext:
    """Extract a bounded upload as untrusted, redacted static text only."""
    extension = PurePath(filename).suffix.lower()
    expected_type = SUPPORTED_RESUME_TYPES.get(extension)
    if expected_type is None or media_type != expected_type:
        raise ResumeParseError("RESUME_UNSUPPORTED_TYPE")
    if not content:
        raise ResumeParseError("RESUME_EMPTY")
    if len(content) > MAX_RESUME_BYTES:
        raise ResumeParseError("RESUME_TOO_LARGE")
    _validate_signature(extension, content)

    extracted = _extract(extension, content)
    normalized_lines = _redact_and_normalize(extracted)
    normalized_text = "\n".join(normalized_lines)
    if not normalized_text:
        raise ResumeParseError("RESUME_EMPTY")

    segments = [
        ResumeSourceSegment(id=_stable_id("segment", index, line), text=line[:500])
        for index, line in enumerate(normalized_lines)
    ]
    context = _structure(segments)
    return ParsedResumeContext(
        content_sha256=hashlib.sha256(content).hexdigest(),
        normalized_text=normalized_text,
        context=context,
    )


def _validate_signature(extension: str, content: bytes) -> None:
    if extension == ".txt":
        if content.startswith((b"%PDF-", b"PK\x03\x04")):
            raise ResumeParseError("RESUME_SIGNATURE_MISMATCH")
        return
    if extension == ".pdf" and not content.startswith(b"%PDF-"):
        raise ResumeParseError("RESUME_SIGNATURE_MISMATCH")
    if extension == ".docx" and not content.startswith(b"PK\x03\x04"):
        raise ResumeParseError("RESUME_SIGNATURE_MISMATCH")


def _extract(extension: str, content: bytes) -> str:
    if extension == ".txt":
        return content.decode("utf-8-sig", errors="replace")
    if extension == ".pdf":
        try:
            reader = PdfReader(BytesIO(content))
            if reader.is_encrypted:
                raise ResumeParseError("RESUME_ENCRYPTED")
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except ResumeParseError:
            raise
        except (PdfReadError, FileNotDecryptedError, OSError, ValueError) as error:
            raise ResumeParseError("RESUME_CORRUPT") from error
    try:
        document = Document(BytesIO(content))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)
    except (BadZipFile, PackageNotFoundError, OSError, ValueError, KeyError) as error:
        raise ResumeParseError("RESUME_CORRUPT") from error


def _redact_and_normalize(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = _CONTROL_PATTERN.sub("", raw_line)
        line = _WHITESPACE_PATTERN.sub(" ", line).strip()
        if not line or _ADDRESS_LINE_PATTERN.search(line):
            continue
        line = _EMAIL_PATTERN.sub("[已脱敏邮箱]", line)
        line = _PHONE_PATTERN.sub("[已脱敏电话]", line)
        if line:
            lines.append(line)
    return lines


def _structure(segments: list[ResumeSourceSegment]) -> CandidateBackground:
    buckets: dict[str, list[ResumeBackgroundItem]] = {
        "education": [], "projects": [], "skills": [], "experiences": []
    }
    current_bucket: str | None = None
    for segment in segments:
        heading_bucket = next((bucket for pattern, bucket in _HEADING_BUCKETS if pattern.match(segment.text)), None)
        if heading_bucket:
            current_bucket = heading_bucket
            continue
        bucket = next((bucket for pattern, bucket in _INLINE_BUCKETS if pattern.match(segment.text)), current_bucket)
        if bucket is None:
            continue
        buckets[bucket].append(
            ResumeBackgroundItem(
                id=_stable_id(bucket, segment.id, segment.text),
                summary=segment.text[:500],
                source_segment_ids=[segment.id],
            )
        )
    return CandidateBackground(source_segments=segments, **buckets)


def _stable_id(*parts: object) -> str:
    joined = "\x1f".join(str(part) for part in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:24]
