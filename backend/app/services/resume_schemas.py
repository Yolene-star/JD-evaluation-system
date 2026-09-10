from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ResumeSourceSegment(BaseModel):
    """A redacted, traceable excerpt of the uploaded document."""

    id: str
    text: str = Field(max_length=500)


class ResumeBackgroundItem(BaseModel):
    """A deterministic background fact; it is never an assessment result."""

    id: str
    summary: str = Field(max_length=500)
    source_segment_ids: list[str] = Field(default_factory=list)


class CandidateBackground(BaseModel):
    source_type: Literal["BACKGROUND_ONLY"] = "BACKGROUND_ONLY"
    education: list[ResumeBackgroundItem] = Field(default_factory=list)
    projects: list[ResumeBackgroundItem] = Field(default_factory=list)
    skills: list[ResumeBackgroundItem] = Field(default_factory=list)
    experiences: list[ResumeBackgroundItem] = Field(default_factory=list)
    summary: str = Field(default="", max_length=500)
    source_segments: list[ResumeSourceSegment] = Field(default_factory=list)


class ParsedResumeContext(BaseModel):
    content_sha256: str = Field(min_length=64, max_length=64)
    normalized_text: str
    context: CandidateBackground
