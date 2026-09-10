# Assessment Agent Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route each stage-two answer through an explicit InterviewAgent with Planner, Memory, and Tool boundaries while preserving all existing APIs, database tables, state-machine rules, evidence traceability, retries, evidence packages, and stage-three reports.

**Architecture:** Add a compatibility facade under `backend/app/agent/`. Existing SQLAlchemy records remain the only memory source, `assessment_state.py` remains the only authority for transitions, and `assessment_service.py` retains API transaction and serialization responsibilities while delegating answer processing to `InterviewAgent`. The frontend consumes one optional `agent_status` snapshot field and renders it inside the existing workbench.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, SQLAlchemy, pytest, React, TypeScript, Vite, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-10-assessment-agent-architecture-design.md`

## Global Constraints

- Do not delete or rename existing assessment routes, request fields, or response fields.
- Do not change existing database tables or add migrations.
- `backend/app/services/assessment_state.py` remains the sole authority for follow-up limits, competency terminal states, current competency progression, and session completion.
- Stage two must not calculate or display formal scores, match percentages, radar charts, or talent-profile conclusions.
- Planner output may explain or select among state-machine-authorized actions, but may not override a state transition.
- Memory is a query projection over existing turns, evidence, and competency assessments; it is not a second source of truth.
- AI output must continue through the existing schema, competency, confidence, and source-excerpt validation.
- Missing API keys and provider failures must retain deterministic demo behavior.
- Preserve all pre-existing uncommitted changes, especially files under analysis, parsing, and configuration.
- Do not commit, push, create a branch, or rewrite history unless the user separately authorizes it.

---

### Task 1: Define Stable Agent Schemas

**Files:**
- Create: `backend/app/agent/__init__.py`
- Create: `backend/app/agent/schemas.py`
- Create: `backend/tests/test_agent_schemas.py`

**Interfaces:**
- Consumes: Pydantic `BaseModel`, Python `StrEnum`.
- Produces: `AgentAction`, `AgentPhase`, `ConversationMemoryItem`, `EvidenceMemoryItem`, `CompetencyMemoryItem`, `PlannerContext`, `PlannerDecision`, `AgentStatus`, and `AgentTurnResult`.

- [ ] **Step 1: Write the failing schema tests**

```python
from pydantic import ValidationError
import pytest

from backend.app.agent.schemas import (
    AgentAction,
    AgentPhase,
    AgentStatus,
    AgentTurnResult,
    PlannerDecision,
)


def test_planner_decision_rejects_unknown_action() -> None:
    with pytest.raises(ValidationError):
        PlannerDecision(action="SCORE", reason="越过阶段二边界")


def test_agent_turn_result_serializes_optional_status_without_api_replacement() -> None:
    result = AgentTurnResult(
        decision=PlannerDecision(
            action=AgentAction.FOLLOW_UP,
            target_competency_id="c-1",
            reason="缺少结果证据",
            question_goal="验证可量化结果",
        ),
        current_question={"id": "q-2", "content": "结果如何衡量？"},
        agent_status=AgentStatus(
            phase=AgentPhase.FOLLOWING_UP,
            confirmed_competency_ids=[],
            active_competency_id="c-1",
            pending_evidence=["项目结果"],
            reason="缺少结果证据",
        ),
    )

    assert result.model_dump()["agent_status"]["active_competency_id"] == "c-1"
    assert result.retryable is False
```

- [ ] **Step 2: Run the tests and confirm the import fails**

Run: `python -m pytest backend/tests/test_agent_schemas.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'backend.app.agent'`.

- [ ] **Step 3: Implement the minimal Pydantic models**

Use string enums with exactly these values:

```python
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
```

Define memory items with stable fields:

```python
class ConversationMemoryItem(BaseModel):
    turn_id: str
    turn_index: int
    role: str
    turn_type: str
    content: str
    covered_competency_ids: list[str] = []


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
```

Use `Field(default_factory=list)` for every list default in production code. `PlannerContext` contains the fields named in the spec. `PlannerDecision.target_competency_id` and `question_goal` default to `None`. `AgentTurnResult.current_question` defaults to `None`; `retryable` defaults to `False`; `error` defaults to `None`.

- [ ] **Step 4: Run the schema tests**

Run: `python -m pytest backend/tests/test_agent_schemas.py -q`

Expected: PASS.

- [ ] **Step 5: Review the task diff without committing**

Run: `git diff --check -- backend/app/agent backend/tests/test_agent_schemas.py`

Expected: exit code 0. Confirm `git status --short` still lists the user's pre-existing files unchanged.

---

### Task 2: Build Read-Only Assessment Memory

**Files:**
- Create: `backend/app/agent/memory.py`
- Create: `backend/tests/test_agent_memory.py`
- Modify: `backend/app/agent/__init__.py`

**Interfaces:**
- Consumes: `AssessmentSession`, `AssessmentTurn`, `EvidenceObservation`, `CompetencyAssessment`, `ConfirmedModelSnapshot`, and Task 1 memory schemas.
- Produces: `AssessmentMemory(db: Session, snapshot_loader=get_confirmed_model_snapshot)` with `get_conversation(session_id)`, `get_evidence(session_id)`, `get_competencies(session)`, and `get_context(session)`.

- [ ] **Step 1: Write failing query-isolation tests**

Create tests using the existing SQLite fixtures and model factories. Seed two sessions with one turn and one observation each, then assert:

```python
memory = AssessmentMemory(db)

conversation = memory.get_conversation(first_session.id)
evidence = memory.get_evidence(first_session.id)
context = memory.get_context(first_session)

assert [item.content for item in conversation] == ["问题一", "回答一"]
assert [item.source_excerpt for item in evidence] == ["回答一"]
assert all(item.turn_id != second_turn.id for item in conversation)
assert context.session_id == first_session.id
assert context.remaining_competency_ids == ["c-2"]
```

Also assert that `get_competencies()` follows confirmed snapshot order rather than database insertion order.

- [ ] **Step 2: Run the tests and confirm the missing class failure**

Run: `python -m pytest backend/tests/test_agent_memory.py -q`

Expected: FAIL importing `AssessmentMemory`.

- [ ] **Step 3: Implement ordered, session-scoped projections**

Queries must include `session_id == requested_session_id`. Order turns by `turn_index`, `created_at`, `id`; order evidence by `created_at`, `id`. Load the immutable snapshot through:

```python
self.snapshot_loader(self.db, session.project_id, session.model_version_id)
```

Build competency items in snapshot order and calculate remaining IDs from statuses not in `{SUFFICIENT, EXHAUSTED, INCOMPLETE}`. Do not mutate or commit any ORM record.

- [ ] **Step 4: Run Memory tests and existing assessment model tests**

Run: `python -m pytest backend/tests/test_agent_memory.py backend/tests/test_assessment_models.py -q`

Expected: PASS.

- [ ] **Step 5: Review the task diff without committing**

Run: `git diff --check -- backend/app/agent backend/tests/test_agent_memory.py`

Expected: exit code 0.

---

### Task 3: Add Thin Tool Adapters

**Files:**
- Create: `backend/app/agent/tools/__init__.py`
- Create: `backend/app/agent/tools/question.py`
- Create: `backend/app/agent/tools/evidence.py`
- Create: `backend/app/agent/tools/scoring.py`
- Create: `backend/app/agent/tools/report.py`
- Create: `backend/tests/test_agent_tools.py`
- Modify: `backend/app/services/assessment_ai.py`

**Interfaces:**
- Consumes: `generate_main_question`, `analyze_answer`, `score_evidence_package`, and `generate_report`.
- Produces: `QuestionTool.generate(...) -> GeneratedQuestion`, `EvidenceTool.analyze(...) -> ValidatedAnalysis`, `ScoringTool.score(package, rubrics) -> EvidencePackageScore`, and `ReportTool.generate(...) -> AssessmentReport`.

- [ ] **Step 1: Write failing adapter delegation tests**

Use injected callables instead of network calls:

```python
def test_question_tool_forwards_agent_context() -> None:
    captured = {}

    def generate(snapshot, competencies, jd_evidence, transcript, transport=None, *, agent_context=None):
        captured["agent_context"] = agent_context
        return GeneratedQuestion(
            content="请说明量化结果",
            covered_competency_ids=["c-1"],
            turn_type="MAIN_QUESTION",
            evaluation_target="验证结果",
            expected_evidence=["指标变化"],
        )

    result = QuestionTool(generate_fn=generate).generate(
        snapshot=object(),
        competencies=[object()],
        jd_evidence=[],
        transcript=[],
        agent_context={"missing_information": ["结果"]},
    )

    assert result.evaluation_target == "验证结果"
    assert captured["agent_context"]["missing_information"] == ["结果"]
```

Add equivalent tests proving EvidenceTool delegates without changing analysis, ScoringTool calls `score_evidence_package`, and ReportTool calls `generate_report`. Assert `InterviewAgent` is not imported by scoring/report modules and those tools do not import stage-two state functions.

- [ ] **Step 2: Run the tests and confirm adapter imports fail**

Run: `python -m pytest backend/tests/test_agent_tools.py -q`

Expected: FAIL because `backend.app.agent.tools` does not exist.

- [ ] **Step 3: Extend GeneratedQuestion compatibly**

Modify `GeneratedQuestion` in `assessment_ai.py`:

```python
evaluation_target: str | None = None
expected_evidence: list[str] = Field(default_factory=list)
```

Add optional keyword-only `agent_context: dict[str, Any] | None = None` to `generate_main_question`. Include it in the structured user payload while preserving all existing positional calls and existing output validation.

- [ ] **Step 4: Implement injected thin adapters**

Each adapter stores its existing service callable in `__init__` and forwards arguments without committing transactions. `QuestionTool` supplies `agent_context`; `EvidenceTool` accepts the existing snapshot, competency, JD evidence, transcript, answer, and optional transport. ScoringTool and ReportTool expose the exact underlying service arguments without importing stage-two modules.

- [ ] **Step 5: Run adapter and AI contract tests**

Run: `python -m pytest backend/tests/test_agent_tools.py backend/tests/test_assessment_ai_contract.py -q`

Expected: PASS, including old provider responses that omit the new question metadata.

- [ ] **Step 6: Review the task diff without committing**

Run: `git diff --check -- backend/app/agent backend/app/services/assessment_ai.py backend/tests/test_agent_tools.py`

Expected: exit code 0.

---

### Task 4: Implement the Deterministic Planner

**Files:**
- Create: `backend/app/agent/planner.py`
- Create: `backend/tests/test_agent_planner.py`
- Modify: `backend/app/agent/__init__.py`

**Interfaces:**
- Consumes: Task 1 `PlannerContext`, `PlannerDecision`, `AgentAction`, and `assessment_state.StateTransition`.
- Produces: `AssessmentPlanner.decide(context, transitions) -> PlannerDecision`.

- [ ] **Step 1: Write failing authority-boundary tests**

Cover all legal paths:

```python
decision = planner.decide(context, [StateTransition("ASK_FOLLOW_UP", "c-1")])
assert decision.action is AgentAction.FOLLOW_UP
assert decision.target_competency_id == "c-1"

decision = planner.decide(context_with_current_c2, [StateTransition("ASK_MAIN_QUESTION", "c-2")])
assert decision.action is AgentAction.NEXT_COMPETENCY
assert decision.target_competency_id == "c-2"

decision = planner.decide(completed_context, [StateTransition("COMPLETE", None)])
assert decision.action is AgentAction.FINISH
assert decision.target_competency_id is None
```

Add tests rejecting an empty transition list, conflicting follow-up targets, a transition target outside `context.competencies`, and a NEXT decision whose target differs from `current_competency_id`.

- [ ] **Step 2: Run the tests and confirm the planner import fails**

Run: `python -m pytest backend/tests/test_agent_planner.py -q`

Expected: FAIL importing `AssessmentPlanner`.

- [ ] **Step 3: Implement deterministic mapping and validation**

Rules:

```text
any ASK_FOLLOW_UP -> FOLLOW_UP for that unique target
session completed or any COMPLETE -> FINISH
otherwise active current competency -> NEXT_COMPETENCY for current_competency_id
```

Reason text must derive from server facts: use the target competency's evidence sufficiency and follow-up count. Do not call an LLM in this task. Raise `PlannerDecisionError` for inconsistent inputs.

- [ ] **Step 4: Run Planner and state-machine tests**

Run: `python -m pytest backend/tests/test_agent_planner.py backend/tests/test_assessment_state.py -q`

Expected: PASS.

- [ ] **Step 5: Review the task diff without committing**

Run: `git diff --check -- backend/app/agent backend/tests/test_agent_planner.py`

Expected: exit code 0.

---

### Task 5: Route Answer Processing Through InterviewAgent

**Files:**
- Create: `backend/app/agent/interview_agent.py`
- Create: `backend/tests/test_interview_agent.py`
- Modify: `backend/app/services/assessment_service.py`
- Modify: `backend/app/agent/__init__.py`

**Interfaces:**
- Consumes: `AssessmentMemory`, `AssessmentPlanner`, `QuestionTool`, `EvidenceTool`, existing event recorder, `apply_analysis`, and Task 1 result schemas.
- Produces: `InterviewAgent(db, memory=None, planner=None, question_tool=None, evidence_tool=None).process_turn(session, answer, retry=False) -> AgentTurnResult`.

- [ ] **Step 1: Write failing InterviewAgent orchestration tests**

Create fixture sessions using existing confirmed-model helpers. Inject fake tools and assert call order through captured markers:

```python
result = agent.process_turn(session, answer)

assert calls == [
    "memory:before",
    "evidence:c-1",
    "state:c-1",
    "memory:after",
    "planner",
    "question:c-1",
]
assert result.decision.action is AgentAction.FOLLOW_UP
assert result.agent_status.phase is AgentPhase.FOLLOWING_UP
```

Add tests for sufficient evidence moving to the next competency, final competency completion, multi-competency evidence isolation, retryable AI failure without state progression, and no scoring/report tool dependency.

- [ ] **Step 2: Run the tests and confirm the missing agent failure**

Run: `python -m pytest backend/tests/test_interview_agent.py -q`

Expected: FAIL importing `InterviewAgent`.

- [ ] **Step 3: Move answer analysis and evidence persistence into InterviewAgent**

Transfer the behavior currently implemented by `_analyze_targets()` and `_process_answer()` without changing event names or order. For each covered competency:

1. resolve the snapshot competency and matching `CompetencyAssessment`;
2. call EvidenceTool;
3. add validated EvidenceObservation rows;
4. record `EVIDENCE_RECORDED`;
5. call `apply_analysis`;
6. record the terminal competency event when applicable.

The Agent may `flush()` but must not `commit()` or `rollback()`.

- [ ] **Step 4: Implement decision, question generation, and status projection**

After all state transitions, reload Memory, call Planner, and:

- generate a targeted follow-up for `FOLLOW_UP`;
- generate a main question for `NEXT_COMPETENCY`;
- record `ASSESSMENT_COMPLETED` for `FINISH`.

Build `AgentStatus` from the post-transition Memory. `pending_evidence` contains the planner reason only for follow-up/retry states; confirmed IDs are competencies in `SUFFICIENT` state.

- [ ] **Step 5: Preserve retry idempotency**

Before writing evidence during a retry, query whether the answer turn already has an `ANSWER_ANALYZED` event. If analysis completed, return the current projection rather than duplicating evidence or questions. Retryable failures record `AI_RETRY_REQUESTED` and return `AgentPhase.RETRY_REQUIRED` without calling `apply_analysis`.

- [ ] **Step 6: Make assessment_service delegate to the Agent**

Keep `submit_turn()` responsible for duplicate idempotency keys, active-session checks, question lookup, USER turn creation, `ANSWER_SUBMITTED`, and top-level error handling. Replace `_process_answer()` body with:

```python
result = InterviewAgent(db).process_turn(session, answer, retry=retry)
db.commit()
return serialize_session(
    db,
    session,
    current_question=result.current_question,
    retryable=result.retryable,
    error=result.error,
    agent_status=result.agent_status,
)
```

Once integration tests pass, remove `_analyze_targets()` and the old duplicated processing loop. Keep `_make_question()` temporarily only for assessment start; do not move start/pause/resume/finish in this task.

- [ ] **Step 7: Run Agent, API, invariant, and evidence-package tests**

Run:

```powershell
python -m pytest backend/tests/test_interview_agent.py backend/tests/test_assessment_api.py backend/tests/test_stage2_invariants.py backend/tests/test_evidence_package.py -q
```

Expected: PASS.

- [ ] **Step 8: Review the task diff without committing**

Run: `git diff --check -- backend/app/agent backend/app/services/assessment_service.py backend/tests/test_interview_agent.py`

Expected: exit code 0.

---

### Task 6: Expose Backward-Compatible Agent Status and Prompt Context

**Files:**
- Modify: `backend/app/services/assessment_service.py`
- Modify: `backend/app/services/assessment_prompts.py`
- Modify: `backend/app/services/assessment_ai.py`
- Modify: `backend/tests/test_assessment_ai_contract.py`
- Modify: `backend/tests/test_assessment_api.py`

**Interfaces:**
- Consumes: Task 1 `AgentStatus`; current assessment response dict; existing AI prompt builders.
- Produces: optional `agent_status` response field and richer question-generation payload with compatible defaults.

- [ ] **Step 1: Write failing response compatibility tests**

Add an API test that submits an answer and asserts all old keys remain plus the optional status:

```python
body = response.json()
assert {
    "session_id",
    "model_version_id",
    "status",
    "completion",
    "current_question",
    "competencies",
    "turns",
    "progress",
    "retryable",
}.issubset(body)
assert body["agent_status"]["phase"] in {
    "FOLLOWING_UP", "MOVING_NEXT", "COMPLETED", "RETRY_REQUIRED"
}
```

Add a GET snapshot test proving `agent_status` may be absent/`None` before the first answer without breaking serialization.

- [ ] **Step 2: Write failing prompt-context tests**

Extend `test_assessment_ai_contract.py` to capture the provider payload and assert it contains `agent_context`, current competency state, existing evidence summaries, missing information, and historical questions. Also assert an old response with only `content`, `covered_competency_ids`, and `turn_type` still validates.

- [ ] **Step 3: Run the focused tests and confirm missing behavior**

Run: `python -m pytest backend/tests/test_assessment_api.py backend/tests/test_assessment_ai_contract.py -q`

Expected: FAIL only on the new status/context assertions.

- [ ] **Step 4: Extend serialization without replacing old fields**

Add `agent_status: AgentStatus | dict | None = None` to `serialize_session()` and append:

```python
"agent_status": (
    agent_status.model_dump(mode="json")
    if isinstance(agent_status, AgentStatus)
    else agent_status
),
```

Do not rename snake_case backend fields. Preserve existing `retryable` and `error` behavior.

- [ ] **Step 5: Enrich prompt construction**

Change `build_question_prompt()` to describe Role, Context, Goal, Constraints, Output Schema, and Evaluation Criteria. It must explicitly prohibit scores and new competencies. The structured payload sent by `generate_main_question()` carries `agent_context` separately; do not interpolate user answers into the system prompt.

- [ ] **Step 6: Run AI contract and API tests**

Run: `python -m pytest backend/tests/test_assessment_ai_contract.py backend/tests/test_assessment_api.py -q`

Expected: PASS.

- [ ] **Step 7: Review the task diff without committing**

Run: `git diff --check -- backend/app/services/assessment_service.py backend/app/services/assessment_prompts.py backend/app/services/assessment_ai.py backend/tests/test_assessment_ai_contract.py backend/tests/test_assessment_api.py`

Expected: exit code 0.

---

### Task 7: Render Agent Status in the Existing Workbench

**Files:**
- Modify: `frontend/src/types/assessment.ts`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/components/AssessmentWorkbench.tsx`
- Modify: `frontend/tests/assessment-ui.spec.tsx`
- Modify: `frontend/src/app/app.css`

**Interfaces:**
- Consumes: optional backend `agent_status` and existing competency names/statuses.
- Produces: optional TypeScript `agentStatus` and an accessible `.agent-status-panel` inside `AssessmentWorkbench`.

- [ ] **Step 1: Write failing UI rendering tests**

Add a snapshot with:

```typescript
agentStatus: {
  phase: 'FOLLOWING_UP',
  confirmedCompetencyIds: ['c1'],
  activeCompetencyId: 'c2',
  pendingEvidence: ['缺少工程结果'],
  reason: '当前能力仍缺少结果证据',
}
```

Assert rendered HTML contains `AI 正在评估`, `系统设计已确认`, `正在验证问题分析`, `等待补充：缺少工程结果`, and the reason. Add a second test proving snapshots without `agentStatus` do not render `AI 正在评估`. Retain the existing assertion that no scoring artifacts appear.

- [ ] **Step 2: Run the focused frontend test and confirm failure**

Run: `npm --prefix frontend run test -- assessment-ui.spec.tsx`

Expected: FAIL because `agentStatus` is not typed or rendered.

- [ ] **Step 3: Add optional frontend types and API mapping**

Define:

```typescript
export type AgentStatus = {
  phase: 'EVALUATING' | 'FOLLOWING_UP' | 'MOVING_NEXT' | 'COMPLETED' | 'RETRY_REQUIRED'
  confirmedCompetencyIds: string[]
  activeCompetencyId?: string
  pendingEvidence: string[]
  reason?: string
}
```

Add `agentStatus?: AgentStatus` to `AssessmentSnapshot`. In `mapAssessmentSnapshot()`, map `agent_status`, `confirmed_competency_ids`, `active_competency_id`, and `pending_evidence` to camelCase while leaving absent status undefined.

- [ ] **Step 4: Render a semantic status section**

Inside `AssessmentWorkbench`, derive competency names from `snapshot.competencies` and render only when `snapshot.agentStatus` exists:

```tsx
<section className="agent-status-panel" aria-labelledby="agent-status-title">
  <h4 id="agent-status-title">AI 正在评估</h4>
  <ul>
    {confirmedNames.map(name => <li key={name}>{name}已确认</li>)}
    {activeName && <li>正在验证{name}</li>}
    {pendingEvidence.map(item => <li key={item}>等待补充：{item}</li>)}
  </ul>
  {reason && <p>{reason}</p>}
</section>
```

Use text for every state; decorative markers must use CSS or `aria-hidden`, not emoji. Do not add a percentage bar or score.

- [ ] **Step 5: Add restrained responsive styling**

Reuse existing surface, border, accent, and text variables/classes in `app.css`. Keep touch targets at least 44px, preserve visible focus styles, avoid horizontal overflow, and add no animation that violates `prefers-reduced-motion`.

- [ ] **Step 6: Run UI tests and frontend build**

Run:

```powershell
npm --prefix frontend run test -- assessment-ui.spec.tsx
npm --prefix frontend run build
```

Expected: both commands exit 0.

- [ ] **Step 7: Review the task diff without committing**

Run: `git diff --check -- frontend/src/types/assessment.ts frontend/src/lib/api.ts frontend/src/components/AssessmentWorkbench.tsx frontend/tests/assessment-ui.spec.tsx frontend/src/app/app.css`

Expected: exit code 0.

---

### Task 8: Complete Regression and Scope Verification

**Files:**
- Modify only if verification exposes a regression: the smallest file and a new regression test reproducing it.
- Review: all files changed by Tasks 1–7.

**Interfaces:**
- Consumes: the completed Agent compatibility facade and all repository test suites.
- Produces: verification evidence that old and new flows coexist without database or API breakage.

- [ ] **Step 1: Run the focused backend Agent suite**

Run:

```powershell
python -m pytest backend/tests/test_agent_schemas.py backend/tests/test_agent_memory.py backend/tests/test_agent_tools.py backend/tests/test_agent_planner.py backend/tests/test_interview_agent.py backend/tests/test_assessment_ai_contract.py backend/tests/test_assessment_api.py backend/tests/test_assessment_state.py backend/tests/test_stage2_invariants.py backend/tests/test_evidence_package.py -q
```

Expected: exit code 0 with no failures.

- [ ] **Step 2: Run the complete backend suite**

Run: `python -m pytest backend/tests -q`

Expected: exit code 0. If a failure is caused by the user's pre-existing parsing work, report it separately and do not modify those files without confirmation.

- [ ] **Step 3: Run complete frontend tests**

Run: `npm --prefix frontend run test`

Expected: exit code 0.

- [ ] **Step 4: Run stage-two Playwright coverage**

Run: `npm --prefix frontend run test:e2e -- stage2.spec.ts`

Expected: exit code 0. This proves create/start/answer/retry/pause/resume/completion behavior through the UI harness.

- [ ] **Step 5: Run the production build**

Run: `npm --prefix frontend run build`

Expected: exit code 0.

- [ ] **Step 6: Verify formatting and database scope**

Run:

```powershell
git diff --check
git diff --name-only
git status --short
```

Expected: no whitespace errors; no migration files; no changes to `backend/app/models.py`; no unrelated edits introduced by this task. Existing user changes remain present and unmodified.

- [ ] **Step 7: Review acceptance criteria against the spec**

Confirm from code and tests:

```text
submit_turn -> InterviewAgent -> EvidenceTool -> assessment_state
            -> AssessmentPlanner -> QuestionTool or FINISH
```

Confirm Agent, Planner, Memory, QuestionTool, EvidenceTool, ScoringTool, and ReportTool are separately importable. Confirm stage two has no scoring/report imports in its runtime dependency path. Confirm all legacy response fields remain available and `agent_status` is optional.

- [ ] **Step 8: Prepare the user handoff without committing**

Report:

- files created and modified;
- focused and full verification commands with exact results;
- confirmation that database structure and public routes were unchanged;
- any remaining limitation, especially that Planner v1 is deterministic and Memory is a query projection;
- the pre-existing unrelated dirty files that were preserved.
