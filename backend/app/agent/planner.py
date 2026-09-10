from collections.abc import Sequence

from ..models import AssessmentSessionStatus
from ..services.assessment_state import StateTransition
from .schemas import AgentAction, PlannerContext, PlannerDecision


class PlannerDecisionError(ValueError):
    pass


class AssessmentPlanner:
    def decide(
        self,
        context: PlannerContext,
        transitions: Sequence[StateTransition],
    ) -> PlannerDecision:
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
        )
