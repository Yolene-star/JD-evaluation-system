import re
from collections.abc import Sequence

from ..models import AssessmentSessionStatus
from ..services.assessment_state import StateTransition
from .schemas import (
    AgentAction,
    FormalPlannerContext,
    PlannerContext,
    PlannerDecision,
    ResumeMemoryContext,
    ResumeReference,
)


class PlannerDecisionError(ValueError):
    pass


class AssessmentPlanner:
    def decide(
        self,
        context: PlannerContext,
        transitions: Sequence[StateTransition],
    ) -> PlannerDecision:
        """Compatibility entry point for callers not yet split into two stages."""
        return self.select_formal_target(context.formal_context(), transitions)

    def select_formal_target(
        self,
        context: FormalPlannerContext,
        transitions: Sequence[StateTransition],
    ) -> PlannerDecision:
        """Choose an assessment target strictly from formal, resume-blind state."""
        if not transitions:
            raise PlannerDecisionError("planner requires a state-machine transition")

        known = {item.competency_id: item for item in context.competencies}
        for item in transitions:
            if item.competency_id is not None and item.competency_id not in known:
                raise PlannerDecisionError("transition target is outside the confirmed model")

        follow_up_targets = {
            item.competency_id
            for item in transitions
            if item.next_action == "ASK_FOLLOW_UP"
        }
        if len(follow_up_targets) > 1:
            raise PlannerDecisionError("planner received conflicting follow-up targets")
        if follow_up_targets:
            target_id = next(iter(follow_up_targets))
            if target_id is None or target_id != context.current_competency_id:
                raise PlannerDecisionError("follow-up target conflicts with current competency")
            target = known[target_id]
            return PlannerDecision(
                action=AgentAction.FOLLOW_UP,
                target_competency_id=target_id,
                reason=(
                    f"{target.name}当前证据{target.evidence_sufficiency}，"
                    f"已追问 {target.follow_up_count} 次，需要继续补充可验证事实"
                ),
                question_goal=f"补充{target.name}的具体做法、依据和结果",
                indicator_ids=list(target.indicator_ids),
                target_indicator_ids=list(target.indicator_ids),
                question_strategy="RESULT_VERIFY" if target.expected_evidence else "DETAIL_PROBE",
                expected_evidence=list(target.expected_evidence),
            )

        completed = (
            context.session_status == AssessmentSessionStatus.COMPLETED.value
            or any(item.next_action == "COMPLETE" for item in transitions)
        )
        if completed:
            if context.current_competency_id is not None:
                raise PlannerDecisionError("completed session cannot retain a current competency")
            return PlannerDecision(
                action=AgentAction.FINISH,
                reason="状态机已确认所有能力项进入终态",
            )

        target_id = context.current_competency_id
        if target_id is None or target_id not in known:
            raise PlannerDecisionError("active session requires a known current competency")
        transition_targets = {
            item.competency_id
            for item in transitions
            if item.next_action == "ASK_MAIN_QUESTION" and item.competency_id is not None
        }
        if transition_targets and transition_targets != {target_id}:
            raise PlannerDecisionError("next competency conflicts with state-machine target")
        target = known[target_id]
        return PlannerDecision(
            action=AgentAction.NEXT_COMPETENCY,
            target_competency_id=target_id,
            reason=f"状态机已推进到下一能力项：{target.name}",
            question_goal=f"获取{target.name}的岗位相关证据",
            indicator_ids=list(target.indicator_ids),
            target_indicator_ids=list(target.indicator_ids),
            question_strategy="OPEN_EXPLORATION",
            expected_evidence=list(target.expected_evidence),
        )

    def select_personalization(
        self,
        formal_target: PlannerDecision,
        resume_context: ResumeMemoryContext | None,
    ) -> ResumeReference | None:
        """Return at most one relevant background hint without changing the decision."""
        if resume_context is None or formal_target.target_competency_id is None:
            return None
        target_tokens = _tokens(
            " ".join(
                value
                for value in (formal_target.question_goal, formal_target.reason)
                if value
            )
        )
        if not target_tokens:
            return None

        candidates = (
            ("project", resume_context.projects),
            ("experience", resume_context.experiences),
            ("skill", resume_context.skills),
            ("education", resume_context.education),
        )
        for item_type, items in candidates:
            for item in items:
                if not _is_relevant(target_tokens, _tokens(item.summary)):
                    continue
                hint = (
                    f"候选人背景提到：{item.summary}。"
                    "请邀请其确认该经历，并说明与本题目标相关的实际贡献。"
                )[:500]
                return ResumeReference(
                    item_id=item.id,
                    item_type=item_type,
                    prompt_hint=hint,
                )
        return None


_TOKEN_PATTERN = re.compile(r"[a-z0-9_+#.]{3,}|[\u4e00-\u9fff]", re.IGNORECASE)


def _tokens(value: str) -> set[str]:
    return {token.lower() for token in _TOKEN_PATTERN.findall(value)}


def _is_relevant(target_tokens: set[str], summary_tokens: set[str]) -> bool:
    overlap = target_tokens & summary_tokens
    if not overlap:
        return False
    # One shared, substantive Latin token (for example, "react") is specific
    # enough; Chinese character overlap needs two characters to avoid generic
    # wording such as "项目" selecting unrelated background.
    return any(any(char.isascii() and char.isalnum() for char in token) for token in overlap) or len(overlap) >= 2
