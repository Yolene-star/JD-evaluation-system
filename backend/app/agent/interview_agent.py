from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    AssessmentEvent,
    AssessmentSession,
    AssessmentSessionStatus,
    AssessmentTurn,
    AssessmentTurnRole,
    AssessmentTurnType,
    CompetencyAssessment,
    CompetencyAssessmentStatus,
    EvidenceObservation,
)
from ..services.assessment_ai import (
    AnalysisResult,
    GeneratedQuestion,
    InvalidAIResponse,
    RetryableAIError,
)
from ..services.assessment_contracts import get_confirmed_model_snapshot
from ..services.assessment_events import record_event
from ..services.assessment_state import StateTransition, apply_analysis
from .memory import AssessmentMemory
from .planner import AssessmentPlanner
from .schemas import (
    AgentAction,
    AgentPhase,
    AgentStatus,
    AgentTurnResult,
    PlannerDecision,
)
from .tools import EvidenceTool, QuestionTool


class AgentProcessingError(ValueError):
    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


class InterviewAgent:
    def __init__(
        self,
        db: Session,
        *,
        memory: AssessmentMemory | None = None,
        planner: AssessmentPlanner | None = None,
        question_tool: QuestionTool | None = None,
        evidence_tool: EvidenceTool | None = None,
    ) -> None:
        self.db = db
        self.memory = memory or AssessmentMemory(db)
        self.planner = planner or AssessmentPlanner()
        self.question_tool = question_tool or QuestionTool()
        self.evidence_tool = evidence_tool or EvidenceTool()

    def process_turn(
        self,
        session: AssessmentSession,
        answer: AssessmentTurn,
        *,
        retry: bool = False,
    ) -> AgentTurnResult:
        if answer.session_id != session.id or answer.role is not AssessmentTurnRole.USER:
            raise AgentProcessingError("ANSWER_SESSION_MISMATCH")
        if retry and self._was_analyzed(session.id, answer.id):
            raise AgentProcessingError("ANSWER_ALREADY_ANALYZED")

        context_before = self.memory.get_context(session)
        snapshot = get_confirmed_model_snapshot(
            self.db,
            session.project_id,
            session.model_version_id,
        )
        snapshot_by_id = {item.id: item for item in snapshot.competencies}
        assessments = {
            item.competency_id: item
            for item in self.db.scalars(
                select(CompetencyAssessment).where(
                    CompetencyAssessment.session_id == session.id
                )
            )
        }
        covered = list(answer.covered_competency_ids or [])
        if not 1 <= len(covered) <= 3 or len(set(covered)) != len(covered):
            raise AgentProcessingError("INVALID_QUESTION_SCOPE")
        if any(item_id not in assessments for item_id in covered):
            raise AgentProcessingError("COMPETENCY_SESSION_MISMATCH")
        if any(item_id not in snapshot_by_id for item_id in covered):
            raise AgentProcessingError("COMPETENCY_NOT_IN_SNAPSHOT")

        analyses: list[tuple[CompetencyAssessment, Any, AnalysisResult]] = []
        transcript = [item.model_dump(mode="json") for item in context_before.conversation]
        for competency_id in covered:
            competency = snapshot_by_id[competency_id]
            try:
                analysis = self.evidence_tool.analyze(
                    snapshot=snapshot,
                    competency=competency,
                    jd_evidence=[],
                    transcript=transcript,
                    answer=answer.content,
                )
            except RetryableAIError as exc:
                return self._retry_result(session, answer, str(exc))
            except InvalidAIResponse as exc:
                raise AgentProcessingError("AI_INVALID_RESPONSE", str(exc)) from exc
            analyses.append((assessments[competency_id], competency, analysis))

        record_event(
            self.db,
            session.id,
            "ANSWER_ANALYZED",
            {"turn_id": answer.id, "retry": retry},
        )
        transitions: list[StateTransition] = []
        analysis_by_id: dict[str, AnalysisResult] = {}
        for target, competency, analysis in analyses:
            analysis_by_id[target.competency_id] = analysis
            for observation in analysis.evidence:
                if observation.competency_id != target.competency_id:
                    raise AgentProcessingError("COMPETENCY_SESSION_MISMATCH")
                self.db.add(
                    EvidenceObservation(
                        session_id=session.id,
                        competency_assessment_id=target.id,
                        competency_id=target.competency_id,
                        turn_id=answer.id,
                        evidence_type=observation.type,
                        excerpt=observation.excerpt,
                        source_excerpt=observation.excerpt,
                        summary=observation.summary,
                        confidence=observation.confidence,
                    )
                )
            record_event(
                self.db,
                session.id,
                "EVIDENCE_RECORDED",
                {"turn_id": answer.id, "competency_id": target.competency_id},
            )
            transition = apply_analysis(session, target, analysis)
            transitions.append(transition)
            if target.status in {
                CompetencyAssessmentStatus.SUFFICIENT,
                CompetencyAssessmentStatus.EXHAUSTED,
            }:
                record_event(
                    self.db,
                    session.id,
                    "COMPETENCY_SUFFICIENT"
                    if target.status is CompetencyAssessmentStatus.SUFFICIENT
                    else "COMPETENCY_EXHAUSTED",
                    {"competency_id": target.competency_id},
                )

        self.db.flush()
        context_after = self.memory.get_context(session)
        formal_decision = self.planner.select_formal_target(context_after.formal_context(), transitions)
        personalization = self.planner.select_personalization(formal_decision, context_after.resume_context)
        question = self._execute_decision(
            session,
            snapshot,
            context_after,
            formal_decision,
            analysis_by_id,
            personalization,
        )
        phase = {
            AgentAction.FOLLOW_UP: AgentPhase.FOLLOWING_UP,
            AgentAction.NEXT_COMPETENCY: AgentPhase.MOVING_NEXT,
            AgentAction.FINISH: AgentPhase.COMPLETED,
        }[formal_decision.action]
        result = AgentTurnResult(
            decision=formal_decision,
            current_question=question,
            agent_status=self._status(context_after, formal_decision, phase),
        )
        self._record_agent_status(session.id, answer.id, result)
        return result

    def _execute_decision(
        self,
        session: AssessmentSession,
        snapshot: Any,
        context: Any,
        decision: PlannerDecision,
        analysis_by_id: dict[str, AnalysisResult],
        resume_reference: Any | None = None,
    ) -> dict[str, Any] | None:
        if decision.action is AgentAction.FINISH:
            record_event(
                self.db,
                session.id,
                "ASSESSMENT_COMPLETED",
                {"completion": session.completion.value},
            )
            return None

        target_id = decision.target_competency_id
        if target_id is None:
            raise AgentProcessingError("PLANNER_TARGET_REQUIRED")
        competency = next(item for item in snapshot.competencies if item.id == target_id)
        if decision.action is AgentAction.FOLLOW_UP:
            analysis = analysis_by_id[target_id]
            question = self.question_tool.generate_follow_up(
                competency=competency,
                analysis=analysis,
                agent_context=context.model_dump(mode="json"),
            )
        else:
            try:
                question = self.question_tool.generate(
                    snapshot=snapshot,
                    competencies=[competency],
                    jd_evidence=[],
                    transcript=[item.model_dump(mode="json") for item in context.conversation],
                    agent_context={
                        "current_competency_state": next(
                            item.model_dump(mode="json")
                            for item in context.competencies
                            if item.competency_id == target_id
                        ),
                        "existing_evidence": [
                            item.model_dump(mode="json")
                            for item in context.evidence
                            if item.competency_id == target_id
                        ],
                        "missing_information": [decision.reason],
                        "historical_questions": [
                            item.content
                            for item in context.conversation
                            if item.role == AssessmentTurnRole.SYSTEM.value
                        ],
                        "formal_target": decision.model_dump(mode="json"),
                    },
                    resume_reference=resume_reference,
                )
            except RetryableAIError:
                question = GeneratedQuestion(
                    content=f"请描述一次与你目标岗位相关的实际项目经历，重点说明你在{competency.name}中的具体做法、依据和结果。",
                    covered_competency_ids=[target_id],
                    turn_type="MAIN_QUESTION",
                    evaluation_target=decision.question_goal,
                )
        return self._persist_question(session, target_id, question)

    def _persist_question(
        self,
        session: AssessmentSession,
        target_id: str,
        question: GeneratedQuestion,
    ) -> dict[str, Any]:
        target = self.db.scalar(
            select(CompetencyAssessment).where(
                CompetencyAssessment.session_id == session.id,
                CompetencyAssessment.competency_id == target_id,
            )
        )
        turn_index = (
            self.db.scalar(
                select(AssessmentTurn.turn_index)
                .where(AssessmentTurn.session_id == session.id)
                .order_by(AssessmentTurn.turn_index.desc())
            )
            or 0
        ) + 1
        turn_type = (
            AssessmentTurnType.FOLLOW_UP
            if question.turn_type == "FOLLOW_UP"
            else AssessmentTurnType.MAIN_QUESTION
        )
        turn = AssessmentTurn(
            session_id=session.id,
            competency_assessment_id=target.id,
            turn_index=turn_index,
            role=AssessmentTurnRole.SYSTEM,
            turn_type=turn_type,
            content=question.content,
            covered_competency_ids=list(question.covered_competency_ids),
        )
        self.db.add(turn)
        self.db.flush()
        if turn_type is AssessmentTurnType.FOLLOW_UP:
            record_event(
                self.db,
                session.id,
                "FOLLOW_UP_GENERATED",
                {"competency_id": target_id, "turn_id": turn.id},
            )
        record_event(
            self.db,
            session.id,
            "QUESTION_GENERATED",
            {
                "turn_id": turn.id,
                "competency_id": target_id,
                "turn_type": turn_type.value,
                "background_reference": question.background_reference,
                "evaluation_target": question.evaluation_target,
                "expected_evidence": list(question.expected_evidence),
            },
        )
        return {
            "id": turn.id,
            "content": turn.content,
            "turn_type": turn.turn_type,
            "covered_competency_ids": list(turn.covered_competency_ids or []),
            "follow_up_target_competency_id": (
                target_id if turn_type is AssessmentTurnType.FOLLOW_UP else None
            ),
            "background_reference": question.background_reference,
        }

    def _retry_result(
        self,
        session: AssessmentSession,
        answer: AssessmentTurn,
        error: str,
    ) -> AgentTurnResult:
        record_event(
            self.db,
            session.id,
            "AI_RETRY_REQUESTED",
            {"turn_id": answer.id, "error": error},
        )
        context = self.memory.get_context(session)
        decision = PlannerDecision(
            action=AgentAction.FOLLOW_UP,
            target_competency_id=session.current_competency_id,
            reason=error,
            question_goal="重试当前回答分析",
        )
        result = AgentTurnResult(
            decision=decision,
            agent_status=self._status(context, decision, AgentPhase.RETRY_REQUIRED),
            retryable=True,
            error=error,
        )
        self._record_agent_status(session.id, answer.id, result)
        return result

    @staticmethod
    def _status(context: Any, decision: PlannerDecision, phase: AgentPhase) -> AgentStatus:
        return AgentStatus(
            phase=phase,
            confirmed_competency_ids=[
                item.competency_id
                for item in context.competencies
                if item.status == CompetencyAssessmentStatus.SUFFICIENT.value
            ],
            active_competency_id=context.current_competency_id,
            pending_evidence=(
                [decision.reason]
                if phase in {AgentPhase.FOLLOWING_UP, AgentPhase.RETRY_REQUIRED}
                else []
            ),
            reason=decision.reason,
        )

    def _was_analyzed(self, session_id: str, turn_id: str) -> bool:
        events = self.db.scalars(
            select(AssessmentEvent).where(
                AssessmentEvent.session_id == session_id,
                AssessmentEvent.action == "ANSWER_ANALYZED",
            )
        )
        return any(json.loads(event.payload).get("turn_id") == turn_id for event in events)

    def _record_agent_status(
        self,
        session_id: str,
        turn_id: str,
        result: AgentTurnResult,
    ) -> None:
        record_event(
            self.db,
            session_id,
            "AGENT_DECISION_RECORDED",
            {
                "turn_id": turn_id,
                "decision": result.decision.model_dump(mode="json"),
                "agent_status": result.agent_status.model_dump(mode="json"),
                "retryable": result.retryable,
            },
        )
