from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from ..services.resume_schemas import ResumeBackgroundItem


class AgentAction(StrEnum):
    FOLLOW_UP = "FOLLOW_UP"
    NEXT_COMPETENCY = "NEXT_COMPETENCY"
    FINISH = "FINISH"


class AgentPhase(StrEnum):
    EVALUATING = "EVALUATING"
    FOLLOWING_UP = "FOLLOWING_UP"
    MOVING_NEXT = "MOVING_NEXT"
    COMPLETED = "COMPLETED"
    RETRY_REQUIRED = "RETRY_REQUIRED"


class ConversationMemoryItem(BaseModel):
    turn_id: str
    turn_index: int
    role: str
    turn_type: str
    content: str
    covered_competency_ids: list[str] = Field(default_factory=list)


class EvidenceMemoryItem(BaseModel):
    evidence_id: str
    competency_id: str
    turn_id: str
    evidence_type: str
    summary: str
    source_excerpt: str
    confidence: float = Field(ge=0, le=1)


class CompetencyMemoryItem(BaseModel):
    competency_id: str
    name: str
    status: str
    follow_up_count: int = Field(ge=0)
    evidence_sufficiency: str
    indicator_ids: list[str] = Field(default_factory=list)
    expected_evidence: list[str] = Field(default_factory=list)


class FormalPlannerContext(BaseModel):
    """The complete planner input for formal assessment decisions.

    This type deliberately has no resume field.  It is the only context
    accepted by the formal target selector.
    """

    session_id: str
    session_status: str
    current_competency_id: str | None = None
    competencies: list[CompetencyMemoryItem] = Field(default_factory=list)
    conversation: list[ConversationMemoryItem] = Field(default_factory=list)
    evidence: list[EvidenceMemoryItem] = Field(default_factory=list)
    remaining_competency_ids: list[str] = Field(default_factory=list)


class ResumeReference(BaseModel):
    item_id: str
    item_type: Literal["education", "project", "skill", "experience"]
    prompt_hint: str = Field(max_length=500)


class ResumeMemoryContext(BaseModel):
    source_type: Literal["BACKGROUND_ONLY"] = "BACKGROUND_ONLY"
    version_id: str
    education: list[ResumeBackgroundItem] = Field(default_factory=list)
    projects: list[ResumeBackgroundItem] = Field(default_factory=list)
    skills: list[ResumeBackgroundItem] = Field(default_factory=list)
    experiences: list[ResumeBackgroundItem] = Field(default_factory=list)


class PlannerContext(FormalPlannerContext):
    """Backward-compatible aggregate memory context with optional background."""

    resume_context: ResumeMemoryContext | None = None

    def formal_context(self) -> FormalPlannerContext:
        return FormalPlannerContext.model_validate(self.model_dump(exclude={"resume_context"}))


class PlannerDecision(BaseModel):
    action: AgentAction
    reason: str
    target_competency_id: str | None = None
    question_goal: str | None = None
    indicator_ids: list[str] = Field(default_factory=list)
    expected_evidence: list[str] = Field(default_factory=list)
    target_indicator_ids: list[str] = Field(default_factory=list)
    question_strategy: Literal["OPEN_EXPLORATION", "DETAIL_PROBE", "TECHNICAL_DEEPEN", "RESULT_VERIFY", "SCENARIO_TEST"] = "OPEN_EXPLORATION"


class AgentStatus(BaseModel):
    phase: AgentPhase
    confirmed_competency_ids: list[str] = Field(default_factory=list)
    active_competency_id: str | None = None
    pending_evidence: list[str] = Field(default_factory=list)
    reason: str | None = None


class AgentTurnResult(BaseModel):
    decision: PlannerDecision
    current_question: dict[str, Any] | None = None
    agent_status: AgentStatus
    retryable: bool = False
    error: str | None = None
