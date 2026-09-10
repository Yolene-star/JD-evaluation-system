from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, String, Text, UniqueConstraint, event
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProjectStatus(StrEnum):
    COLLECTING = "COLLECTING"
    ANALYZING = "ANALYZING"
    REVIEWING = "REVIEWING"
    CONFIRMED = "CONFIRMED"
    ARCHIVED = "ARCHIVED"


class JobDescriptionStatus(StrEnum):
    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ModelVersionStatus(StrEnum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[ProjectStatus] = mapped_column(Enum(ProjectStatus), default=ProjectStatus.COLLECTING)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    job_descriptions: Mapped[list["JobDescription"]] = relationship(back_populates="project")


class JobDescription(Base):
    __tablename__ = "job_descriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    raw_text: Mapped[str] = mapped_column(Text)
    status: Mapped[JobDescriptionStatus] = mapped_column(Enum(JobDescriptionStatus), default=JobDescriptionStatus.RECEIVED)
    participates_in_model: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    project: Mapped[Project] = relationship(back_populates="job_descriptions")


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    jd_id: Mapped[str] = mapped_column(ForeignKey("job_descriptions.id"), index=True)
    excerpt: Mapped[str] = mapped_column(Text)
    start_offset: Mapped[int] = mapped_column(default=0)
    end_offset: Mapped[int] = mapped_column(default=0)


class Competency(Base):
    __tablename__ = "competencies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    jd_id: Mapped[str] = mapped_column(ForeignKey("job_descriptions.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(50), default="competency")
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    weight: Mapped[float] = mapped_column(Float, default=0.0)


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    version: Mapped[str] = mapped_column(String(20), default="draft")
    status: Mapped[ModelVersionStatus] = mapped_column(Enum(ModelVersionStatus), default=ModelVersionStatus.DRAFT)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ModelSnapshot(Base):
    __tablename__ = "model_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    model_version_id: Mapped[str] = mapped_column(ForeignKey("model_versions.id"), unique=True, index=True)
    version: Mapped[str] = mapped_column(String(20))
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConflictDecisionRecord(Base):
    __tablename__ = "conflict_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    model_version_id: Mapped[str] = mapped_column(ForeignKey("model_versions.id"), index=True)
    conflict_key: Mapped[str] = mapped_column(String(400))
    decision: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    action: Mapped[str] = mapped_column(String(80))
    payload: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LLMCallLog(Base):
    __tablename__ = "llm_call_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    task_type: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(120))
    prompt_version: Mapped[str] = mapped_column(String(40), default="stage1-chat-v1")
    status: Mapped[str] = mapped_column(String(30))
    latency_ms: Mapped[int | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AssessmentSessionStatus(StrEnum):
    READY = "READY"
    IN_PROGRESS = "IN_PROGRESS"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    PARTIALLY_FINISHED = "PARTIALLY_FINISHED"
    FAILED = "FAILED"


class AssessmentCompletion(StrEnum):
    NONE = "NONE"
    FULL = "FULL"
    PARTIAL = "PARTIAL"


class CompetencyAssessmentStatus(StrEnum):
    PENDING = "PENDING"
    ASKING = "ASKING"
    FOLLOW_UP = "FOLLOW_UP"
    SUFFICIENT = "SUFFICIENT"
    EXHAUSTED = "EXHAUSTED"
    INCOMPLETE = "INCOMPLETE"


class CompetencyAssessmentEvidenceSufficiency(StrEnum):
    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT = "INSUFFICIENT"
    UNCERTAIN = "UNCERTAIN"


class AssessmentTurnRole(StrEnum):
    SYSTEM = "SYSTEM"
    USER = "USER"


class AssessmentTurnType(StrEnum):
    MAIN_QUESTION = "MAIN_QUESTION"
    ANSWER = "ANSWER"
    FOLLOW_UP = "FOLLOW_UP"


class EvidenceType(StrEnum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    MISSING = "MISSING"
    UNCERTAIN = "UNCERTAIN"


class AssessmentSession(Base):
    __tablename__ = "assessment_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    model_version_id: Mapped[str] = mapped_column(ForeignKey("model_versions.id"), index=True)
    status: Mapped[AssessmentSessionStatus] = mapped_column(Enum(AssessmentSessionStatus), default=AssessmentSessionStatus.READY)
    completion: Mapped[AssessmentCompletion] = mapped_column(Enum(AssessmentCompletion), default=AssessmentCompletion.NONE)
    # References the immutable confirmed-snapshot competency ID, not a mutable stage-one row.
    current_competency_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CompetencyAssessment(Base):
    __tablename__ = "competency_assessments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(ForeignKey("assessment_sessions.id"), index=True)
    # Snapshot competency IDs are immutable version-local IDs, not live stage-one rows.
    competency_id: Mapped[str] = mapped_column(String(36), index=True)
    status: Mapped[CompetencyAssessmentStatus] = mapped_column(Enum(CompetencyAssessmentStatus), default=CompetencyAssessmentStatus.PENDING)
    follow_up_count: Mapped[int] = mapped_column(default=0)
    main_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_sufficiency: Mapped[CompetencyAssessmentEvidenceSufficiency] = mapped_column(Enum(CompetencyAssessmentEvidenceSufficiency), default=CompetencyAssessmentEvidenceSufficiency.UNCERTAIN)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AssessmentTurn(Base):
    __tablename__ = "assessment_turns"
    __table_args__ = (UniqueConstraint("session_id", "idempotency_key", name="uq_assessment_turn_idempotency"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(ForeignKey("assessment_sessions.id"), index=True)
    competency_assessment_id: Mapped[str | None] = mapped_column(ForeignKey("competency_assessments.id"), nullable=True, index=True)
    turn_index: Mapped[int] = mapped_column(default=0)
    role: Mapped[AssessmentTurnRole] = mapped_column(Enum(AssessmentTurnRole))
    turn_type: Mapped[AssessmentTurnType] = mapped_column(Enum(AssessmentTurnType))
    content: Mapped[str] = mapped_column(Text)
    covered_competency_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EvidenceObservation(Base):
    __tablename__ = "evidence_observations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(ForeignKey("assessment_sessions.id"), index=True)
    competency_assessment_id: Mapped[str] = mapped_column(ForeignKey("competency_assessments.id"), index=True)
    competency_id: Mapped[str] = mapped_column(String(36), index=True)
    turn_id: Mapped[str] = mapped_column(ForeignKey("assessment_turns.id"), index=True)
    evidence_type: Mapped[EvidenceType] = mapped_column(Enum(EvidenceType))
    excerpt: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, default="")
    source_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AssessmentEvent(Base):
    __tablename__ = "assessment_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(ForeignKey("assessment_sessions.id"), index=True)
    action: Mapped[str] = mapped_column(String(80))
    payload: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RubricSetStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class AssessmentReportStatus(StrEnum):
    GENERATING = "GENERATING"
    READY = "READY"
    FAILED = "FAILED"


class ReportNarrativeStatus(StrEnum):
    PENDING = "PENDING"
    GENERATING = "GENERATING"
    READY = "READY"
    PENDING_RETRY = "PENDING_RETRY"
    FAILED = "FAILED"


class AssessmentReportCompletion(StrEnum):
    FULL = "FULL"
    PARTIAL = "PARTIAL"


class RubricSet(Base):
    __tablename__ = "rubric_sets"
    __table_args__ = (UniqueConstraint("model_version_id", "version", name="uq_rubric_model_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    model_version_id: Mapped[str] = mapped_column(ForeignKey("model_versions.id"), index=True)
    version: Mapped[str] = mapped_column(String(40))
    status: Mapped[RubricSetStatus] = mapped_column(Enum(RubricSetStatus), default=RubricSetStatus.DRAFT)
    scoring_rule_version: Mapped[str] = mapped_column(String(40), default="stage3-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    competencies: Mapped[list["CompetencyRubric"]] = relationship(back_populates="rubric_set", cascade="all, delete-orphan")


class CompetencyRubric(Base):
    __tablename__ = "competency_rubrics"
    __table_args__ = (UniqueConstraint("rubric_set_id", "competency_id", name="uq_rubric_competency"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    rubric_set_id: Mapped[str] = mapped_column(ForeignKey("rubric_sets.id"), index=True)
    competency_id: Mapped[str] = mapped_column(String(36), index=True)
    rubric_version: Mapped[str] = mapped_column(String(40), default="stage3-v1")
    level_0_2: Mapped[str] = mapped_column(Text, default="无有效正向证据，或存在严重反向证据")
    level_3_4: Mapped[str] = mapped_column(Text, default="只有零散理解，主要指标未覆盖")
    level_5_6: Mapped[str] = mapped_column(Text, default="覆盖基础指标，可完成常规任务")
    level_7_8: Mapped[str] = mapped_column(Text, default="覆盖主要指标，可处理常规及部分复杂场景")
    level_9_10: Mapped[str] = mapped_column(Text, default="覆盖全部核心指标，并能说明权衡、边界和实践经验")
    indicators: Mapped[list[str]] = mapped_column(JSON, default=list)
    scoring_rules: Mapped[dict] = mapped_column(JSON, default=dict)
    rubric_set: Mapped[RubricSet] = relationship(back_populates="competencies")


class AssessmentReport(Base):
    __tablename__ = "assessment_reports"
    __table_args__ = (UniqueConstraint("assessment_session_id", "evidence_package_id", "rubric_set_id", "scoring_rule_version", "report_version", name="uq_report_snapshot"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    assessment_session_id: Mapped[str] = mapped_column(ForeignKey("assessment_sessions.id"), index=True)
    report_version: Mapped[int] = mapped_column(default=1)
    evidence_package_id: Mapped[str] = mapped_column(String(36), index=True)
    model_version_id: Mapped[str] = mapped_column(ForeignKey("model_versions.id"), index=True)
    rubric_set_id: Mapped[str] = mapped_column(ForeignKey("rubric_sets.id"), index=True)
    scoring_rule_version: Mapped[str] = mapped_column(String(40), default="stage3-v1")
    completion: Mapped[AssessmentReportCompletion] = mapped_column(Enum(AssessmentReportCompletion))
    evaluated_weight: Mapped[float] = mapped_column(Float, default=0.0)
    unevaluated_weight: Mapped[float] = mapped_column(Float, default=0.0)
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    match_score_type: Mapped[str] = mapped_column(String(20), default="NONE")
    status: Mapped[AssessmentReportStatus] = mapped_column(Enum(AssessmentReportStatus), default=AssessmentReportStatus.GENERATING)
    narrative_status: Mapped[ReportNarrativeStatus] = mapped_column(Enum(ReportNarrativeStatus), default=ReportNarrativeStatus.PENDING)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    evaluations: Mapped[list["CompetencyEvaluation"]] = relationship(back_populates="report", cascade="all, delete-orphan")
    narrative: Mapped["ReportNarrative | None"] = relationship(back_populates="report", uselist=False, cascade="all, delete-orphan")


class CompetencyEvaluation(Base):
    __tablename__ = "competency_evaluations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    report_id: Mapped[str] = mapped_column(ForeignKey("assessment_reports.id"), index=True)
    competency_id: Mapped[str] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(String(20))
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    attainment: Mapped[float | None] = mapped_column(Float, nullable=True)
    level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    matched_indicator_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    negative_evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    missing_indicator_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    rationale: Mapped[str] = mapped_column(Text, default="")
    report: Mapped[AssessmentReport] = relationship(back_populates="evaluations")


class ReportNarrative(Base):
    __tablename__ = "report_narratives"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    report_id: Mapped[str] = mapped_column(ForeignKey("assessment_reports.id"), unique=True, index=True)
    overview: Mapped[str] = mapped_column(Text, default="")
    strengths: Mapped[list] = mapped_column(JSON, default=list)
    weaknesses: Mapped[list] = mapped_column(JSON, default=list)
    recommendations: Mapped[list] = mapped_column(JSON, default=list)
    cited_evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    report: Mapped[AssessmentReport] = relationship(back_populates="narrative")


@event.listens_for(RubricSet, "before_update")
def prevent_active_rubric_mutation(mapper: object, connection: object, target: RubricSet) -> None:
    state = sa_inspect(target)
    status_history = state.attrs.status.history
    old_status = status_history.deleted[0] if status_history.deleted else target.status
    # Transitioning ACTIVE -> RETIRED is the one allowed mutation used when
    # activating a replacement version; all other updates to an active set
    # must be made by creating a new version.
    if old_status is RubricSetStatus.ACTIVE and target.status is RubricSetStatus.ACTIVE:
        raise ValueError("active rubric sets are immutable; create a new version")


@event.listens_for(CompetencyRubric, "before_update")
def prevent_active_rubric_child_mutation(mapper: object, connection: object, target: CompetencyRubric) -> None:
    row = connection.execute(
        RubricSet.__table__.select().with_only_columns(RubricSet.status).where(RubricSet.id == target.rubric_set_id)
    ).scalar_one_or_none()
    if row in {RubricSetStatus.ACTIVE, RubricSetStatus.ACTIVE.value}:
        raise ValueError("competencies in an active rubric set are immutable; create a new version")
