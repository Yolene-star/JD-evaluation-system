import pytest

from backend.app.agent.planner import AssessmentPlanner, PlannerDecisionError
from backend.app.agent.schemas import (
    AgentAction,
    CompetencyMemoryItem,
    FormalPlannerContext,
    PlannerContext,
    ResumeMemoryContext,
)
from backend.app.models import AssessmentSessionStatus
from backend.app.services.resume_schemas import ResumeBackgroundItem
from backend.app.services.assessment_state import StateTransition


def context(
    *,
    status: str = "IN_PROGRESS",
    current: str | None = "c-1",
) -> PlannerContext:
    return PlannerContext(
        session_id="s-1",
        session_status=status,
        current_competency_id=current,
        competencies=[
            CompetencyMemoryItem(
                competency_id="c-1",
                name="系统设计",
                status="FOLLOW_UP" if current == "c-1" else "SUFFICIENT",
                follow_up_count=1,
                evidence_sufficiency="INSUFFICIENT",
            ),
            CompetencyMemoryItem(
                competency_id="c-2",
                name="问题分析",
                status="ASKING" if current == "c-2" else "PENDING",
                follow_up_count=0,
                evidence_sufficiency="UNCERTAIN",
            ),
        ],
        remaining_competency_ids=[item for item in (current,) if item],
    )


def transition(action: str, target: str | None = None, *, completed: bool = False) -> StateTransition:
    current_status = (
        AssessmentSessionStatus.COMPLETED
        if completed
        else AssessmentSessionStatus.IN_PROGRESS
    )
    return StateTransition(
        previous_status=AssessmentSessionStatus.IN_PROGRESS,
        current_status=current_status,
        next_action=action,
        competency_id=target,
    )


def test_planner_uses_state_machine_follow_up_target() -> None:
    decision = AssessmentPlanner().decide(
        context(),
        [transition("ASK_FOLLOW_UP", "c-1")],
    )

    assert decision.action is AgentAction.FOLLOW_UP
    assert decision.target_competency_id == "c-1"
    assert "证据" in decision.reason


def test_formal_target_is_resume_blind_and_personalization_is_bounded() -> None:
    """Would fail if a resume could influence the frozen formal target."""
    formal_context = FormalPlannerContext(
        session_id="s-1",
        session_status="IN_PROGRESS",
        current_competency_id="c-1",
        competencies=[
            CompetencyMemoryItem(
                competency_id="c-1",
                name="系统设计",
                status="FOLLOW_UP",
                follow_up_count=1,
                evidence_sufficiency="INSUFFICIENT",
                indicator_ids=["说明技术选型依据"],
                expected_evidence=["本人行动", "可验证结果"],
            )
        ],
        remaining_competency_ids=["c-1"],
    )
    resume_context = ResumeMemoryContext(
        version_id="resume-v1",
        projects=[
            ResumeBackgroundItem(id="project-1", summary="系统设计平台项目", source_segment_ids=[])
        ],
        skills=[
            ResumeBackgroundItem(id="resume-only-skill", summary="摄影", source_segment_ids=[])
        ],
    )
    planner = AssessmentPlanner()
    transitions = [transition("ASK_FOLLOW_UP", "c-1")]

    without_resume = planner.select_formal_target(formal_context, transitions)
    with_resume = planner.select_formal_target(formal_context, transitions)
    reference = planner.select_personalization(with_resume, resume_context)

    assert "resume_context" not in formal_context.model_dump()
    assert with_resume.target_competency_id == without_resume.target_competency_id == "c-1"
    assert with_resume.question_goal == without_resume.question_goal
    assert with_resume.indicator_ids == without_resume.indicator_ids == ["说明技术选型依据"]
    assert with_resume.expected_evidence == without_resume.expected_evidence == ["本人行动", "可验证结果"]
    assert with_resume.target_competency_id != "resume-only-skill"
    assert reference is not None
    assert reference.item_id == "project-1"
    assert reference.item_type == "project"


def test_legacy_planner_context_projects_only_formal_fields() -> None:
    """Would fail if compatibility context leaked optional resume data into formal planning."""
    resume_context = ResumeMemoryContext(
        version_id="resume-v1",
        skills=[ResumeBackgroundItem(id="skill-1", summary="Python", source_segment_ids=[])],
    )
    legacy_context = context().model_copy(update={"resume_context": resume_context})

    formal_context = legacy_context.formal_context()

    assert formal_context.model_dump() == context().model_dump(exclude={"resume_context"})
    assert "resume_context" not in formal_context.model_dump()


def test_planner_uses_server_current_competency_for_next_question() -> None:
    decision = AssessmentPlanner().decide(
        context(current="c-2"),
        [transition("ASK_MAIN_QUESTION", "c-2")],
    )

    assert decision.action is AgentAction.NEXT_COMPETENCY
    assert decision.target_competency_id == "c-2"


def test_planner_finishes_only_after_state_machine_completion() -> None:
    decision = AssessmentPlanner().decide(
        context(status="COMPLETED", current=None),
        [transition("COMPLETE", completed=True)],
    )

    assert decision.action is AgentAction.FINISH
    assert decision.target_competency_id is None


@pytest.mark.parametrize(
    ("planner_context", "transitions"),
    [
        (context(), []),
        (
            context(),
            [
                transition("ASK_FOLLOW_UP", "c-1"),
                transition("ASK_FOLLOW_UP", "c-2"),
            ],
        ),
        (context(), [transition("ASK_FOLLOW_UP", "outside")]),
        (context(current="c-2"), [transition("ASK_MAIN_QUESTION", "c-1")]),
    ],
)
def test_planner_rejects_decisions_that_conflict_with_state_machine(
    planner_context: PlannerContext,
    transitions: list[StateTransition],
) -> None:
    with pytest.raises(PlannerDecisionError):
        AssessmentPlanner().decide(planner_context, transitions)
