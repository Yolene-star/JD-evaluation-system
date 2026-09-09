# 阶段二自适应测评 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在阶段一已确认岗位胜任力模型之上，实现可暂停、可恢复、可追问的文字测评闭环，并输出供阶段三消费的结构化证据包。

**Architecture:** 阶段二作为阶段一模块化单体中的独立领域模块实现。后端使用显式 `AssessmentSession` 与 `CompetencyAssessment` 状态机控制顺序、轮次、幂等和完成条件；AI 只通过结构化 Schema 生成问题、分析回答和提取证据。前端复用全局 AppShell、ConversationTimeline、StageWorkbench 和 EvidenceDrawer，补充测评专属工作台、回答输入、处理中、重试和完成卡片。

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, React, TypeScript, Vitest, Playwright, pytest；沿用阶段一已配置的 AI 兼容接口和数据库运行方式。

**Spec:** `docs/superpowers/specs/2026-09-09-stage2-adaptive-assessment-design.md`

## Global Constraints

- MVP 只支持文字输入和文字输出。
- 阶段二只读取阶段一 `CONFIRMED` 的模型版本，不修改能力项、权重或 JD 证据。
- 程序负责状态、顺序、轮次、权限、Schema 校验和幂等；AI 负责问题生成、回答理解、证据提取和自然语言追问。
- 每个核心能力项包含 1 道主问题，最多 2 次追问。
- 一道主问题可以综合覆盖不超过 3 个相关能力项；证据和追问仍按能力项独立计算。
- 单项题与综合题共用同一套页面骨架；单项题隐藏覆盖标签和多能力证据分配面板，只高亮当前能力项。
- AI 不得创建新能力项、修改权重或直接推进会话状态。
- 每个回答必须保留原文、轮次和可追溯证据；阶段三只消费版本化证据包。
- 阶段二不计算正式分数、岗位匹配度、雷达图或人才画像。
- 桌面端沿用三栏 AppShell；窄屏将右侧工作台改为右侧抽屉；不得产生核心内容横向滚动。
- 所有状态变化同时写入领域记录和 `AssessmentEvent`；已完成会话不可追加回答。

---

### Task 1: 建立阶段二领域模型、枚举和阶段一快照适配器

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/main.py`
- Create: `backend/app/services/assessment_contracts.py`
- Create: `backend/tests/test_assessment_models.py`

**Interfaces:**
- `AssessmentSessionStatus = READY | IN_PROGRESS | PAUSED | COMPLETED | PARTIALLY_FINISHED | FAILED`。
- `CompetencyAssessmentStatus = PENDING | ASKING | FOLLOW_UP | SUFFICIENT | EXHAUSTED | INCOMPLETE`。
- `AssessmentTurnRole = SYSTEM | USER`；`AssessmentTurnType = MAIN_QUESTION | ANSWER | FOLLOW_UP`。
- `AssessmentTurn.covered_competency_ids: list[str]`：系统问题保存覆盖范围，用户回答轮次继承该范围。
- `EvidenceType = POSITIVE | NEGATIVE | MISSING | UNCERTAIN`。
- `get_confirmed_model_snapshot(project_id: str, model_version_id: str | None = None) -> ConfirmedModelSnapshot`：只能返回已确认版本，否则抛出明确的 `ModelNotConfirmedError`。
- `ConfirmedModelSnapshot` 包含 `model_version_id` 和按稳定顺序排列的核心能力项，每项至少含 `id`、`name`、`description`、`weight`、`jd_evidence_ids`。

- [ ] **Step 1: Write failing model and snapshot tests**

```python
def test_snapshot_rejects_draft_model(session, draft_model):
    with pytest.raises(ModelNotConfirmedError):
        get_confirmed_model_snapshot(draft_model.project_id, draft_model.id)

def test_assessment_session_defaults_to_ready(session, confirmed_model):
    created = create_assessment_session(session, confirmed_model.project_id, confirmed_model.id)
    assert created.status == AssessmentSessionStatus.READY
    assert created.current_competency_id is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backend/tests/test_assessment_models.py -q`
Expected: FAIL because assessment models and confirmed-snapshot adapter do not exist.

- [ ] **Step 3: Add SQLAlchemy models and Pydantic schemas**

Add `AssessmentSession`, `CompetencyAssessment`, `AssessmentTurn`, `EvidenceObservation` and `AssessmentEvent` with UUID string IDs, UTC timestamps, foreign keys and indexes on session/current competency/idempotency key. Add `covered_competency_ids` to system turns (and copy it onto the related answer turn) using a JSON column or normalized join table consistent with the existing stage-one database style. Add uniqueness for `(session_id, idempotency_key)` where an idempotency key is present. Extend app initialization so tables are created in the same test database path used by stage one.

- [ ] **Step 4: Implement the confirmed-model snapshot adapter**

Read only the immutable confirmed model and its competencies/evidence references. Preserve stored competency order or use explicit `position`; never sort by AI output. Return a typed snapshot used by every later task.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest backend/tests/test_assessment_models.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models.py backend/app/schemas.py backend/app/main.py backend/app/services/assessment_contracts.py backend/tests/test_assessment_models.py
git commit -m "feat: add assessment domain models and confirmed snapshot contract"
```

### Task 2: Implement deterministic assessment state machine and event service

**Files:**
- Create: `backend/app/services/assessment_state.py`
- Create: `backend/app/services/assessment_events.py`
- Create: `backend/tests/test_assessment_state.py`

**Interfaces:**
- `start_session(session, snapshot) -> StateTransition`：`READY -> IN_PROGRESS`，初始化第一个 `CompetencyAssessment`。
- `select_question_scope(snapshot, pending_competencies) -> list[str]`：返回一个能力项或不超过 3 个相关能力项，供综合题使用；不得选择已进入终态的能力项。
- `pause_session(session) -> StateTransition`：只允许 `IN_PROGRESS -> PAUSED`。
- `resume_session(session) -> StateTransition`：只允许 `PAUSED -> IN_PROGRESS`。
- `finish_session(session, reason: str) -> StateTransition`：创建 `PARTIALLY_FINISHED` 和 `INCOMPLETE` 能力项状态。
- `apply_analysis(session, competency_assessment, analysis: AnalysisResult) -> StateTransition`：严格执行充分证据/最多两次追问/切换下一能力项规则；综合题的每个目标能力项分别调用并分别推进。
- `record_event(session_id, action, payload) -> AssessmentEvent`：写入结构化事件，不删除或覆盖旧事件。

- [ ] **Step 1: Write failing transition tests**

```python
def test_insufficient_answer_creates_first_follow_up(session, active_assessment):
    result = apply_analysis(session, active_assessment, insufficient_analysis())
    assert result.next_action == "ASK_FOLLOW_UP"
    assert active_assessment.follow_up_count == 1
    assert active_assessment.status == CompetencyAssessmentStatus.FOLLOW_UP

def test_third_insufficient_answer_exhausts_competency(session, active_assessment):
    active_assessment.follow_up_count = 2
    result = apply_analysis(session, active_assessment, insufficient_analysis())
    assert result.next_action == "ADVANCE"
    assert active_assessment.status == CompetencyAssessmentStatus.EXHAUSTED
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backend/tests/test_assessment_state.py -q`
Expected: FAIL because transition functions do not exist.

- [ ] **Step 3: Implement guarded transitions**

Make invalid transitions raise typed domain errors. `apply_analysis` must treat the program rule as authoritative: `SUFFICIENT` advances immediately; non-sufficient analysis with count `< 2` requests one follow-up for that target competency only; count `== 2` marks that target `EXHAUSTED`. A composite question may therefore mark two competencies `SUFFICIENT` while keeping a third in `FOLLOW_UP`. When no pending competency remains, mark the session `COMPLETED` and set completion to `FULL`.

- [ ] **Step 4: Implement event creation in the same transaction boundary**

Emit the exact event names from the spec, including `ASSESSMENT_CREATED`, `ASSESSMENT_STARTED`, `ANSWER_SUBMITTED`, `ANSWER_ANALYZED`, `EVIDENCE_RECORDED`, `FOLLOW_UP_GENERATED`, `COMPETENCY_SUFFICIENT`, `COMPETENCY_EXHAUSTED`, `ASSESSMENT_PAUSED`, `ASSESSMENT_RESUMED`, `ASSESSMENT_COMPLETED`, `ASSESSMENT_PARTIALLY_FINISHED`, `AI_RETRY_REQUESTED` and `AI_INVALID_RESPONSE`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest backend/tests/test_assessment_state.py -q`
Expected: PASS, including invalid transition coverage.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/assessment_state.py backend/app/services/assessment_events.py backend/tests/test_assessment_state.py
git commit -m "feat: add assessment state machine and audit events"
```

### Task 3: Add AI question-generation and answer-analysis contracts

**Files:**
- Create: `backend/app/services/assessment_ai.py`
- Create: `backend/app/services/assessment_prompts.py`
- Create: `backend/tests/test_assessment_ai_contract.py`
- Modify: `backend/app/config.py`

**Interfaces:**
- `generate_main_question(snapshot, competencies, jd_evidence, transcript) -> GeneratedQuestion`：`competencies` 长度为 1–3，并返回 `covered_competency_ids`。
- `analyze_answer(snapshot, competency, jd_evidence, transcript, answer) -> AnalysisResult`。
- `AnalysisResult` fields: `answer_summary`, `evidence`, `evidence_sufficiency`, `needs_follow_up`, `follow_up_reason`, `follow_up_question`；每个 `evidence` 必须带 `competency_id`，且只能属于本题 `covered_competency_ids`。
- `validate_source_excerpt(answer: str, excerpt: str) -> bool`：支持精确匹配，并对空白归一化后再匹配。
- `validate_analysis(result, answer, competency_id) -> ValidatedAnalysis`：拒绝枚举越界、置信度越界、空追问和越权能力引用。

- [ ] **Step 1: Write failing contract tests**

```python
def test_excerpt_not_in_answer_is_downgraded_to_uncertain():
    result = validate_analysis(valid_result(source_excerpt="不存在"), "用户回答原文", "c1")
    assert result.evidence[0].type == EvidenceType.UNCERTAIN

def test_confidence_out_of_range_is_rejected():
    with pytest.raises(InvalidAIResponse):
        validate_analysis(valid_result(confidence=1.2), "回答", "c1")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backend/tests/test_assessment_ai_contract.py -q`
Expected: FAIL because the AI contracts and validators do not exist.

- [ ] **Step 3: Implement Pydantic response schemas and validators**

Validate all fields before persistence. Normalize whitespace only for matching; preserve the original answer and original excerpt for display. If an excerpt cannot be located, retain it as an `UNCERTAIN` observation with a validation note rather than silently inventing a location. For a composite question, group observations by `competency_id` and run sufficiency validation independently for each group; never mark all covered competencies sufficient from one global boolean.

- [ ] **Step 4: Implement prompt builders and AI adapter calls**

Prompt inputs must be limited to the current competency, its JD evidence, current competency transcript and fixed rules. Use the existing OpenAI-compatible adapter/configuration from stage one. The adapter must return parsed structured output or a typed retryable error; it must never mutate database state.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest backend/tests/test_assessment_ai_contract.py -q`
Expected: PASS using mocked adapter responses.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/assessment_ai.py backend/app/services/assessment_prompts.py backend/app/config.py backend/tests/test_assessment_ai_contract.py
git commit -m "feat: add structured assessment ai contracts"
```

### Task 4: Implement assessment session and turn APIs with idempotency

**Files:**
- Create: `backend/app/routes/assessments.py`
- Create: `backend/app/services/assessment_service.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_assessment_api.py`

**Interfaces:**
- `POST /api/projects/{project_id}/assessments` accepts `{model_version_id?: string}` and returns a `READY` session.
- `GET /api/assessments/{session_id}` returns session status, current competency, recent turns, progress and retryability.
- `POST /api/assessments/{session_id}/start` generates the first main question.
- `POST /api/assessments/{session_id}/turns` accepts `{content: string, idempotency_key: string}` and returns `session_status`, `current_competency`, `next_message`, `progress`, `retryable`.
- `POST /api/assessments/{session_id}/pause`, `/resume`, `/finish`, `/retry` implement the state transitions from Task 2.
- `GET /api/assessments/{session_id}/events` returns ordered audit events.

- [ ] **Step 1: Write failing API tests**

```python
def test_create_start_and_submit_answer(client, confirmed_project):
    session = client.post(f"/api/projects/{confirmed_project.id}/assessments").json()
    started = client.post(f"/api/assessments/{session['id']}/start")
    assert started.status_code == 200
    response = client.post(
        f"/api/assessments/{session['id']}/turns",
        json={"content": "我在项目中做过容量评估", "idempotency_key": "turn-1"},
    )
    assert response.status_code == 200
    assert response.json()["progress"]["total"] > 0

def test_duplicate_idempotency_key_returns_same_result(client, active_session):
    payload = {"content": "同一回答", "idempotency_key": "same-key"}
    first = client.post(f"/api/assessments/{active_session.id}/turns", json=payload)
    second = client.post(f"/api/assessments/{active_session.id}/turns", json=payload)
    assert first.json() == second.json()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backend/tests/test_assessment_api.py -q`
Expected: FAIL because routes and service orchestration do not exist.

- [ ] **Step 3: Implement session creation and access checks**

Require the project to be accessible to the current user and the model version to be confirmed. Create one `CompetencyAssessment` per snapshot competency lazily or eagerly, but expose a stable total count. Write `ASSESSMENT_CREATED` in the same transaction.

- [ ] **Step 4: Implement start and answer orchestration**

For `/start`, select one or up to three pending related competencies, generate the main question and a `SYSTEM / MAIN_QUESTION` turn with `covered_competency_ids`. For `/turns`, validate active state and non-empty text, deduplicate by `(session_id, idempotency_key)`, persist the user answer with inherited coverage before AI analysis, validate AI output, persist evidence grouped by competency, call the state machine once per affected competency, then create either a targeted follow-up for the remaining gap or the next question. On AI failure, commit the answer and retryable event without advancing any covered competency.

- [ ] **Step 5: Implement pause, resume, finish, retry and event listing**

Paused sessions reject answer submission with a stable error code. `finish` returns the number of incomplete competencies and requires an explicit confirmation flag. `retry` is only valid after a retryable AI error and reuses the saved answer; it must not create a duplicate answer turn.

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest backend/tests/test_assessment_api.py -q`
Expected: PASS, including access checks, idempotency and retry behavior.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routes/assessments.py backend/app/services/assessment_service.py backend/app/main.py backend/tests/test_assessment_api.py
git commit -m "feat: add assessment session and turn api"
```

### Task 5: Implement versioned evidence-package export for stage three

**Files:**
- Create: `backend/app/services/evidence_package.py`
- Create: `backend/app/routes/evidence_packages.py`
- Create: `backend/tests/test_evidence_package.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- `build_evidence_package(session_id: str) -> EvidencePackage`：只读会话、能力评估、turn 和 evidence 记录。
- `GET /api/assessments/{session_id}/evidence-package` returns `FULL` or `PARTIAL` package with model version ID, competency statuses, observations and turn IDs.

- [ ] **Step 1: Write failing package tests**

```python
def test_full_package_contains_traceable_observations(completed_session):
    package = build_evidence_package(completed_session.id)
    assert package.completion == "FULL"
    assert all(item.turn_ids for item in package.competencies)
    assert all(obs.turn_id for item in package.competencies for obs in item.observations)

def test_partial_package_marks_unfinished_items(partial_session):
    package = build_evidence_package(partial_session.id)
    assert package.completion == "PARTIAL"
    assert any(item.status == "INCOMPLETE" for item in package.competencies)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backend/tests/test_evidence_package.py -q`
Expected: FAIL because package builder and route do not exist.

- [ ] **Step 3: Implement immutable package projection**

Build the package from persisted records, not transient AI output. Include `session_id`, `model_version_id`, completion type, competency status, observations, source excerpts, confidence and referenced turn IDs. Do not include scores or image/report fields.

- [ ] **Step 4: Add package route and authorization**

Allow access only to the owning project/user. Permit packages for `COMPLETED` and `PARTIALLY_FINISHED`; reject `READY`, `IN_PROGRESS` and `PAUSED` with a stable not-ready response.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest backend/tests/test_evidence_package.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/evidence_package.py backend/app/routes/evidence_packages.py backend/app/main.py backend/tests/test_evidence_package.py
git commit -m "feat: export versioned assessment evidence package"
```

### Task 6: Build the stage-two desktop and responsive UI

**Files:**
- Create: `frontend/src/components/AssessmentIntroCard.tsx`
- Create: `frontend/src/components/QuestionBubble.tsx`
- Create: `frontend/src/components/AnswerComposer.tsx`
- Create: `frontend/src/components/ThinkingIndicator.tsx`
- Create: `frontend/src/components/EvidenceInlineCard.tsx`
- Create: `frontend/src/components/AssessmentCompletionCard.tsx`
- Create: `frontend/src/components/RetryNotice.tsx`
- Create: `frontend/src/components/AssessmentWorkbench.tsx`
- Modify: `frontend/src/components/StageWorkbench.tsx`
- Modify: `frontend/src/components/ConversationTimeline.tsx`
- Modify: `frontend/src/app/App.tsx`
- Modify: `frontend/src/app/app.css`
- Modify: `frontend/src/lib/api.ts`
- Create: `frontend/src/types/assessment.ts`
- Create: `frontend/tests/assessment-ui.spec.tsx`

**Interfaces:**
- `AssessmentApi` exposes `create`, `get`, `start`, `submitTurn`, `pause`, `resume`, `finish`, `retry`, `getEvidencePackage`.
- `AssessmentWorkbench` receives session snapshot and callbacks; it never infers state locally.
- `QuestionBubble` receives `coveredCompetencies` and renders a composite-question label plus competency tags.
- `EvidenceInlineCard` receives grouped observations keyed by competency ID and renders independent sufficiency/follow-up states.
- `AnswerComposer` emits only `{content, idempotencyKey}` and disables submit while pending.

- [ ] **Step 1: Write failing component tests**

```tsx
it('shows progress and current competency', () => {
  render(<AssessmentWorkbench session={fixtureSession} />);
  expect(screen.getByText('3 / 8 个能力项')).toBeInTheDocument();
  expect(screen.getByText('系统设计')).toHaveAttribute('aria-current', 'step');
});

it('disables duplicate submit while analyzing', async () => {
  render(<AnswerComposer status="ANALYZING" onSubmit={vi.fn()} />);
  expect(screen.getByRole('button', {name: '提交回答'})).toBeDisabled();
  expect(screen.getByText('正在分析回答')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm --prefix frontend run test -- assessment-ui.spec.tsx`
Expected: FAIL because stage-two components and types do not exist.

- [ ] **Step 3: Add typed API client and assessment fixtures**

Add request/response types matching the backend contracts. Use server snapshots as the source of truth; after every mutation replace local state with the response rather than manually incrementing progress.

- [ ] **Step 4: Implement conversation components**

Render intro, system question/follow-up, user answer, analysis indicator, inline evidence summary, retry notice and completion card. For composite questions, show “综合题 · 覆盖 N 项能力”, render one tag per covered competency, and group evidence by competency so the user can see why only one capability receives a follow-up. For single-competency questions, show one competency tag, direct evidence summary and a targeted follow-up label without the multi-competency allocation panel; keep the same shell, input position and workbench structure. Preserve the answer draft until the server acknowledges it. Announce status changes with an `aria-live="polite"` region.

- [ ] **Step 5: Implement the right workbench**

Show session status, `completed / total` progress, current competency, all competency states, evidence summary and pause/resume/finish controls. Finish uses `ConfirmDialog` and states how many items remain plus the `PARTIAL` result behavior.

- [ ] **Step 6: Implement responsive behavior and accessibility**

At desktop keep the workbench visible; at `768px` and below expose it as a right-side drawer with focus trap, Escape close and focus return. Use 44px minimum touch targets, visible focus rings, labels on icon buttons, no color-only states, no horizontal overflow and `prefers-reduced-motion` fallbacks. Keep the global warm-white/low-saturation teal tokens; do not introduce purple gradients.

- [ ] **Step 7: Run tests and production build**

Run: `npm --prefix frontend run test -- assessment-ui.spec.tsx` and `npm --prefix frontend run build`
Expected: PASS and successful production build.

- [ ] **Step 8: Commit**

```bash
git add frontend/src frontend/tests/assessment-ui.spec.tsx
git commit -m "feat: add stage two assessment ui"
```

### Task 7: Add end-to-end recovery, completion and browser-flow coverage

**Files:**
- Create: `backend/tests/test_stage2_invariants.py`
- Create: `frontend/tests/stage2.spec.ts`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-09-09-stage2-adaptive-assessment-design.md`

**Interfaces:**
- Browser flow starts from a confirmed stage-one model and exercises start, answer, follow-up, pause, resume, completion and evidence package viewing.
- Invariant tests verify no duplicate idempotency records, max two follow-ups, immutable model version reference, complete event sequence and traceable evidence.

- [ ] **Step 1: Write failing backend invariant tests**

```python
def test_session_never_exceeds_two_followups(client, active_session):
    for index in range(4):
        client.post(f"/api/assessments/{active_session.id}/turns", json={"content": "不足", "idempotency_key": f"k-{index}"})
    state = client.get(f"/api/assessments/{active_session.id}").json()
    assert state["current_competency"]["follow_up_count"] <= 2

def test_completed_session_has_traceable_event_and_package(client, completed_session):
    events = client.get(f"/api/assessments/{completed_session.id}/events").json()
    package = client.get(f"/api/assessments/{completed_session.id}/evidence-package").json()
    assert any(event["action"] == "ASSESSMENT_COMPLETED" for event in events)
    assert package["completion"] == "FULL"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backend/tests/test_stage2_invariants.py -q`
Expected: FAIL until all previous tasks are integrated.

- [ ] **Step 3: Write the browser flow**

Cover: open confirmed project, enter stage two, create session, start, answer main question, observe follow-up, pause, reload, resume, finish all competencies, open evidence package, and confirm no score/radar chart appears in stage two.

- [ ] **Step 4: Add failure-path browser coverage**

Mock AI timeout and invalid structured response. Assert the user answer remains visible, retry action appears, duplicate submit is prevented, and successful retry returns to the same competency.

- [ ] **Step 5: Update documentation**

Document the stage-two API endpoints, required confirmed model prerequisite, AI environment variables already used by stage one, demo/mock adapter behavior, local test commands and the distinction between `FULL` and `PARTIAL` evidence packages. Keep stage three scoring explicitly marked as not implemented.

- [ ] **Step 6: Run the full verification suite**

Run:

```bash
python -m pytest backend/tests -q
npm --prefix frontend run test
npm --prefix frontend run test:e2e
npm --prefix frontend run build
git diff --check
```

Expected: all automated tests pass, build succeeds, and there are no whitespace errors.

- [ ] **Step 7: Commit the stage-two handoff**

```bash
git add backend frontend README.md docs/superpowers/specs/2026-09-09-stage2-adaptive-assessment-design.md
git commit -m "feat: complete stage two adaptive assessment flow"
```

---

## Plan Self-Review

- **Spec coverage:** Tasks 1–2 cover the session and competency state machines, immutable stage-one snapshot and event audit. Task 3 covers question/answer AI contracts and excerpt validation. Task 4 covers every assessment API, pause/resume/finish/retry and idempotency. Task 5 covers the versioned `FULL`/`PARTIAL` evidence package. Task 6 covers the approved UI structure, responsive drawer, accessibility and all visual states. Task 7 covers integration, failure recovery, documentation and acceptance verification.
- **Dependency boundary:** No task assumes stage-one internals beyond the named confirmed-model snapshot adapter. If stage one uses different concrete model names, only Task 1's adapter maps them into the stable `ConfirmedModelSnapshot`; the rest of the plan remains unchanged.
- **Placeholder scan:** Every step contains concrete files, interfaces, tests, commands and expected outcomes; no unresolved placeholder instructions remain.
- **Type consistency:** `AnalysisResult`, `ConfirmedModelSnapshot`, `AssessmentSessionStatus`, `CompetencyAssessmentStatus`, API payloads and evidence-package fields are defined before later tasks consume them.
- **Scope:** This plan implements only the stage-two text assessment and its evidence handoff. Voice, code execution, multi-person interviews and stage-three scoring remain explicitly out of scope.
