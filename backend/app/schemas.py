from datetime import datetime

from pydantic import BaseModel, ConfigDict

from .models import (
    AssessmentCompletion,
    AssessmentSessionStatus,
    AssessmentTurnRole,
    AssessmentTurnType,
    CompetencyAssessmentEvidenceSufficiency,
    CompetencyAssessmentStatus,
    EvidenceType,
    JobDescriptionStatus,
    ProjectStatus,
)


class HealthResponse(BaseModel):
    status: str


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime


class ProjectCreate(BaseModel):
    name: str


class JobDescriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    title: str
    raw_text: str
    status: JobDescriptionStatus
    participates_in_model: bool
    created_at: datetime


class TextJdCreate(BaseModel):
    title: str
    text: str


class LinkJdCreate(BaseModel):
    url: str


class JdUpdate(BaseModel):
    title: str | None = None
    participates_in_model: bool | None = None


class AssessmentSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    model_version_id: str
    status: AssessmentSessionStatus
    completion: AssessmentCompletion = AssessmentCompletion.NONE
    current_competency_id: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    paused_at: datetime | None = None
    completed_at: datetime | None = None


class CompetencyAssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    competency_id: str
    status: CompetencyAssessmentStatus
    follow_up_count: int
    created_at: datetime
    main_question: str | None = None
    evidence_sufficiency: CompetencyAssessmentEvidenceSufficiency = CompetencyAssessmentEvidenceSufficiency.UNCERTAIN
    started_at: datetime | None = None
    completed_at: datetime | None = None


class AssessmentTurnResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    competency_assessment_id: str | None = None
    turn_index: int = 0
    role: AssessmentTurnRole
    turn_type: AssessmentTurnType
    content: str
    covered_competency_ids: list[str]
    idempotency_key: str | None = None
    created_at: datetime


class EvidenceObservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    competency_assessment_id: str
    competency_id: str
    turn_id: str
    evidence_type: EvidenceType
    excerpt: str
    summary: str = ""
    source_excerpt: str | None = None
    confidence: float
    created_at: datetime


class AssessmentEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    action: str
    payload: str
    created_at: datetime


# Stable aliases for callers that use the schema suffix convention.
AssessmentSessionSchema = AssessmentSessionResponse
CompetencyAssessmentSchema = CompetencyAssessmentResponse
AssessmentTurnSchema = AssessmentTurnResponse
EvidenceObservationSchema = EvidenceObservationResponse
AssessmentEventSchema = AssessmentEventResponse
