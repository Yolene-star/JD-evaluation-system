# 阶段一 JD解析与岗位胜任力模型 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现阶段一的可执行垂直切片：用户能够创建任务、添加多份 JD、查看解析状态、生成单份与总岗位胜任力模型、处理冲突、查看证据并确认冻结模型版本。

**Architecture:** 使用 FastAPI 模块化单体后端和 React + TypeScript 前端。后端以任务、JD、能力项、证据、模型版本和事件为核心领域对象；AI 适配层先提供 DeepSeek/OpenAI 兼容接口，同时保留确定性演示解析器，使没有 API Key 时仍可执行完整 UI 流程。前端使用统一 AppShell，左侧直接列出历史任务，中央为对话，右侧为阶段一工作台。

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, SQLAlchemy, SQLite 开发数据库/PostgreSQL 兼容模型, React, TypeScript, Vite, Vitest, Playwright。

**Spec:** `design/00-全局交互基线设计.md`、`design/01-阶段一-JD解析与岗位胜任力模型设计.md`

## Global Constraints

- 原文与清洗结果分开保存，任何正式能力项必须引用 JD 证据。
- AI只负责语义理解，状态、权限、Schema、权重计算和版本冻结由程序控制。
- 总模型能力权重之和必须为100%，经验、证书和其他约束不得混入能力权重。
- 已确认模型必须冻结；后续修改只能创建新草稿版本。
- 工作台操作和对话命令写入同一领域事件，并显示系统操作卡片。
- 左侧导航只保留新建任务、历史任务和展开/折叠；当前任务在历史列表中高亮。
- 桌面端右侧工作台常驻，窄屏改为右侧滑出；核心内容不得依赖横向滚动。
- 原型文件只作为交互参考，生产代码收敛到统一组件，不逐页复制原型。

---

### Task 1: 建立前后端工程骨架与统一领域模型

**Files:**
- Create: `backend/app/main.py`
- Create: `backend/app/config.py`
- Create: `backend/app/db.py`
- Create: `backend/app/models.py`
- Create: `backend/app/schemas.py`
- Create: `backend/tests/test_health.py`
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/app/App.tsx`
- Create: `frontend/src/app/app.css`
- Create: `frontend/src/lib/api.ts`

**Interfaces:**
- `GET /api/health` returns `{status: "ok"}`.
- `Project`, `JobDescription`, `Competency`, `Evidence`, `ModelVersion`, `AuditEvent` are SQLAlchemy models with UUID string IDs and UTC timestamps.
- `ProjectStatus` is `COLLECTING | ANALYZING | REVIEWING | CONFIRMED | ARCHIVED`.
- Frontend `App` renders the shared shell with placeholder data and no stage-specific business logic.

- [ ] **Step 1: Write the failing health test**

```python
from fastapi.testclient import TestClient
from app.main import app

def test_health_returns_ok():
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest backend/tests/test_health.py -q`
Expected: FAIL because `backend/app/main.py` does not exist.

- [ ] **Step 3: Implement the minimal backend and models**

Create the FastAPI app, SQLite session factory, declarative models, Pydantic enums, and `/api/health`. Keep database initialization in `create_app()` so tests can override the database URL.

- [ ] **Step 4: Create the minimal Vite shell**

Create a TypeScript entry point, a single `App` component, and CSS tokens for the warm-white/low-saturation teal visual baseline. The initial shell must have three regions: history navigation, conversation area, and stage workbench.

- [ ] **Step 5: Run backend and frontend checks**

Run: `python -m pytest backend/tests/test_health.py -q` and `npm --prefix frontend run build`
Expected: PASS and a successful Vite production build.

- [ ] **Step 6: Commit**

```bash
git add backend frontend
git commit -m "chore: scaffold stage one application shell"
```

### Task 2: Implement project, history task, JD intake, and audit events

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/models.py`
- Modify: `backend/app/schemas.py`
- Create: `backend/app/routes/projects.py`
- Create: `backend/app/routes/jds.py`
- Create: `backend/app/services/audit.py`
- Create: `backend/tests/test_jd_intake.py`
- Modify: `frontend/src/app/App.tsx`
- Create: `frontend/src/components/HistoryNav.tsx`
- Create: `frontend/src/components/ConversationTimeline.tsx`
- Create: `frontend/src/components/MaterialDialog.tsx`
- Create: `frontend/src/components/OperationCard.tsx`
- Modify: `frontend/src/lib/api.ts`

**Interfaces:**
- `POST /api/projects` accepts `{name: string}` and returns a project with `status: "COLLECTING"`.
- `GET /api/projects` returns recent projects ordered by `updated_at DESC`.
- `POST /api/projects/{project_id}/jds/text` accepts `{title: string, text: string}` and returns a JD with `status: "RECEIVED"` plus an audit event.
- `POST /api/projects/{project_id}/jds/file` accepts multipart `file` and returns the same JD shape.
- `POST /api/projects/{project_id}/jds/link` accepts `{url: string}` and records a pending fetch source without bypassing authentication or robots restrictions.
- `GET /api/projects/{project_id}/events` returns operation events used by the conversation timeline.
- `PATCH /api/jds/{jd_id}` supports `title` and `participates_in_model`; setting `false` means temporarily removed, not deleted.

- [ ] **Step 1: Write failing API tests**

```python
def test_text_jd_creates_audited_record(client):
    project = client.post("/api/projects", json={"name": "产品岗位模型"}).json()
    response = client.post(f"/api/projects/{project['id']}/jds/text", json={"title": "前端JD", "text": "负责 React 组件开发"})
    assert response.status_code == 201
    assert response.json()["status"] == "RECEIVED"
    events = client.get(f"/api/projects/{project['id']}/events").json()
    assert events[0]["action"] == "JD_ADDED"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest backend/tests/test_jd_intake.py -q`
Expected: FAIL because project and JD routes are missing.

- [ ] **Step 3: Implement project and JD routes**

Implement route validation, ownership checks through the project ID boundary, text size limits, safe URL protocol validation, and audit event creation in the same transaction as the mutation.

- [ ] **Step 4: Implement history navigation and material dialog**

Render recent tasks directly in `HistoryNav`; highlight the active task, show stage/status/time, keep only new task/history/expand controls, and move the four JD intake modes into `MaterialDialog` opened from the composer.

- [ ] **Step 5: Verify event cards and responsive shell**

Run: `npm --prefix frontend run build` and `python -m pytest backend/tests/test_jd_intake.py -q`
Expected: PASS; operation cards show action, object, result, and a compact impact summary.

- [ ] **Step 6: Commit**

```bash
git add backend frontend
git commit -m "feat: add project history and jd intake"
```

### Task 3: Add deterministic parsing pipeline and evidence-backed single JD model

**Files:**
- Create: `backend/app/services/parsing.py`
- Create: `backend/app/services/weights.py`
- Create: `backend/app/routes/analysis.py`
- Create: `backend/tests/test_parsing_pipeline.py`
- Create: `frontend/src/components/StageRail.tsx`
- Create: `frontend/src/components/StageWorkbench.tsx`
- Create: `frontend/src/components/JdPicker.tsx`
- Create: `frontend/src/components/SingleJdModel.tsx`
- Create: `frontend/src/components/EvidenceView.tsx`
- Modify: `frontend/src/app/App.tsx`

**Interfaces:**
- `POST /api/projects/{project_id}/analysis/run` starts parsing and returns `{project_status: "ANALYZING", job_ids: [...]}`.
- `GET /api/projects/{project_id}/analysis` returns project progress, JD statuses, single-JD competencies, evidence, and warnings.
- `POST /api/jds/{jd_id}/retry` returns the JD with status `RECEIVED`.
- `parse_jd(text: str) -> ParsedJd` returns requirements, qualifications, constraints, and evidence spans.
- `calculate_competency_weight(coverage: float, intensity: float, task_criticality: float, level: float) -> float` returns a non-negative normalized factor.

- [ ] **Step 1: Write failing parser and weight tests**

```python
def test_parser_creates_evidence_for_each_competency():
    parsed = parse_jd("负责 React 组件开发，优化页面性能")
    assert {item.name for item in parsed.competencies} == {"组件化开发", "性能优化"}
    assert all(item.evidence_ids for item in parsed.competencies)

def test_weight_formula_normalizes_to_one():
    values = [calculate_competency_weight(.8, .9, .7, .6), calculate_competency_weight(.5, .4, .5, .4)]
    assert abs(sum(normalize_weights(values)) - 1.0) < 1e-9
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backend/tests/test_parsing_pipeline.py -q`
Expected: FAIL because parsing and weight services do not exist.

- [ ] **Step 3: Implement deterministic extraction and evidence spans**

Implement a small versioned rule/lexicon pipeline for the MVP. It must classify ability, qualification, certificate, and constraint; preserve exact source text and character offsets; return `unknown` rather than inventing a competency.

- [ ] **Step 4: Implement analysis routes and status transitions**

Process each participating JD independently, isolate failures, persist evidence before model rows, and transition `COLLECTING -> ANALYZING -> REVIEWING`. Use the fixed weight formula from the stage-one design and keep qualifications outside competency weights.

- [ ] **Step 5: Implement single-JD workbench**

Build the top stage rail, the two tabs `总模型` and `单份 JD 模型`, the search dropdown with empty-query-all behavior, compact competency rows, removed-JD grouping, and evidence view with read-only source text and highlighted spans.

- [ ] **Step 6: Verify**

Run: `python -m pytest backend/tests/test_parsing_pipeline.py -q` and `npm --prefix frontend run build`
Expected: PASS with an accessible single-JD model view.

- [ ] **Step 7: Commit**

```bash
git add backend frontend
git commit -m "feat: add evidence-backed jd analysis"
```

### Task 4: Implement total model aggregation, conflict review, editing, and re-add flow

**Files:**
- Create: `backend/app/services/aggregation.py`
- Create: `backend/app/routes/models.py`
- Create: `backend/tests/test_model_review.py`
- Create: `frontend/src/components/TotalModel.tsx`
- Create: `frontend/src/components/CompetencyDetail.tsx`
- Create: `frontend/src/components/ConflictDecision.tsx`
- Create: `frontend/src/components/CompetencyEditor.tsx`
- Create: `frontend/src/components/ReaddJd.tsx`
- Modify: `frontend/src/components/StageWorkbench.tsx`

**Interfaces:**
- `POST /api/projects/{project_id}/aggregate` returns a draft `ModelVersion` with `status: "DRAFT"`.
- `GET /api/models/{model_id}` returns conclusion-first competency rows, conflict count, evidence summaries, and weight factors.
- `POST /api/models/{model_id}/conflicts/{conflict_id}/resolve` accepts `{decision: "MERGE" | "SEPARATE" | "RENAME_MERGE", name?: string}`.
- `PATCH /api/competencies/{competency_id}` accepts draft-only name/category/level/weight changes and returns an impact preview.
- `POST /api/jds/{jd_id}/readd` restores participation and returns recalculation status.

- [ ] **Step 1: Write failing aggregation tests**

```python
def test_aggregation_separates_competencies_and_qualifications():
    model = aggregate([jd_with("React组件开发", kind="competency"), jd_with("本科", kind="qualification")])
    assert model.competencies[0].weight > 0
    assert model.qualifications[0].name == "本科"
    assert abs(sum(item.weight for item in model.competencies) - 1.0) < 1e-9

def test_confirmed_model_cannot_be_mutated():
    model = confirm_model(draft_model())
    with pytest.raises(ImmutableModelError):
        update_competency(model, name="新名称")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backend/tests/test_model_review.py -q`
Expected: FAIL because aggregation and review routes are missing.

- [ ] **Step 3: Implement aggregation and draft-only mutations**

Group normalized competencies, preserve source JD IDs and evidence IDs, detect low-confidence name/level conflicts, calculate the fixed four-factor weight, and reject mutations against confirmed versions.

- [ ] **Step 4: Implement review components**

Use a compact single-column workbench: conclusion-first total model, detail view with evidence, conflict decision options, editor with save-before-impact preview, and removed-JD re-add flow. Keep original source read-only.

- [ ] **Step 5: Verify**

Run: `python -m pytest backend/tests/test_model_review.py -q` and `npm --prefix frontend run build`
Expected: PASS; draft changes show affected weights and confirmed models remain read-only.

- [ ] **Step 6: Commit**

```bash
git add backend frontend
git commit -m "feat: add total model review workflow"
```

### Task 5: Implement confirmation, immutable snapshot, export, and failure recovery

**Files:**
- Create: `backend/app/routes/confirmation.py`
- Create: `backend/app/routes/export.py`
- Create: `backend/tests/test_confirmation.py`
- Create: `frontend/src/components/FinalReview.tsx`
- Create: `frontend/src/components/CompletedStage.tsx`
- Create: `frontend/src/components/ParseFailure.tsx`
- Modify: `frontend/src/components/StageWorkbench.tsx`

**Interfaces:**
- `POST /api/models/{model_id}/confirm` returns immutable `ModelSnapshot` version `v1.0` only when no blocking conflicts remain.
- `GET /api/models/{model_id}/export` returns a downloadable JSON document containing model, evidence references, decisions, and version metadata.
- `GET /api/jds/{jd_id}/failure` returns failure stage, reason, source metadata, and allowed recovery actions.
- `POST /api/jds/{jd_id}/retry` requeues only that JD and does not duplicate the record.

- [ ] **Step 1: Write failing confirmation tests**

```python
def test_confirmation_requires_no_blocking_conflicts(client, draft_model):
    response = client.post(f"/api/models/{draft_model['id']}/confirm")
    assert response.status_code == 409
    assert response.json()["code"] == "BLOCKING_CONFLICTS"

def test_confirmation_creates_immutable_snapshot(client, resolved_draft):
    response = client.post(f"/api/models/{resolved_draft['id']}/confirm")
    assert response.status_code == 201
    assert response.json()["version"] == "v1.0"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backend/tests/test_confirmation.py -q`
Expected: FAIL because confirmation routes and snapshot rules are missing.

- [ ] **Step 3: Implement confirmation and export**

Require all blocking conflicts resolved, create a new immutable snapshot, write `MODEL_CONFIRMED` audit event, and export only the confirmed snapshot plus traceable evidence metadata.

- [ ] **Step 4: Implement final review and completion views**

Add final check summary, blocking/non-blocking risk display, frozen-version completion state, and explicit `进入阶段二` navigation that does not start an interview.

- [ ] **Step 5: Implement failure recovery view**

Show failure stage and reason, offer OCR retry/re-upload/paste-text alternatives, keep the failed source record, and isolate retry state from other JD tasks.

- [ ] **Step 6: Verify**

Run: `python -m pytest backend/tests -q` and `npm --prefix frontend run build`
Expected: PASS; confirmation is blocked correctly and export contains no unreferenced competency.

- [ ] **Step 7: Commit**

```bash
git add backend frontend
git commit -m "feat: confirm and export stage one model"
```

### Task 6: End-to-end verification and stage-one handoff

**Files:**
- Create: `frontend/tests/stage1.spec.ts`
- Create: `backend/tests/test_stage1_invariants.py`
- Modify: `README.md`
- Modify: `design/01-阶段一-JD解析与岗位胜任力模型设计.md`

**Interfaces:**
- Browser flow starts at `/`, creates a project, adds two text JD records, runs analysis, opens single-JD evidence, resolves a conflict, confirms the model, and downloads the snapshot.
- Backend invariant test checks evidence coverage, weight sum, immutable snapshot, audit event sequence, and no duplicate JD after retry.

- [ ] **Step 1: Write the end-to-end test**

```ts
test('stage one completes with traceable model', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: '新建任务' }).click();
  await page.getByLabel('任务名称').fill('产品岗位模型');
  await page.getByRole('button', { name: '创建任务' }).click();
  await page.getByRole('button', { name: '添加材料' }).click();
  await page.getByRole('tab', { name: '粘贴文字' }).click();
  await page.getByLabel('JD标题').fill('产品经理 JD');
  await page.getByLabel('JD正文').fill('负责需求分析和跨团队协作');
  await page.getByRole('button', { name: '添加到项目' }).click();
  await page.getByRole('button', { name: '生成总模型' }).click();
  await page.getByRole('button', { name: '确认并冻结 v1.0' }).click();
  await expect(page.getByText('岗位胜任力模型已确认')).toBeVisible();
});
```

- [ ] **Step 2: Run the invariant and browser tests**

Run: `python -m pytest backend/tests -q` and `npm --prefix frontend run test:e2e`
Expected: PASS with no evidence, weight, state, or duplicate-record violations.

- [ ] **Step 3: Run production build and diff checks**

Run: `npm --prefix frontend run build` and `git diff --check`
Expected: successful build and no whitespace errors.

- [ ] **Step 4: Update quick-start documentation**

Document backend setup, frontend setup, DeepSeek-compatible environment variables, demo-parser fallback, and the stage-one acceptance flow without claiming stage two is implemented.

- [ ] **Step 5: Commit the handoff**

```bash
git add backend frontend README.md design/01-阶段一-JD解析与岗位胜任力模型设计.md frontend/tests backend/tests
git commit -m "docs: hand off verified stage one workflow"
```

---

## Plan Self-Review

- Spec coverage: the plan covers unified shell/navigation, four JD intake modes, asynchronous parsing states, evidence traceability, single and total models, conflict review, draft editing, remove/re-add, confirmation, export, audit events, and stage-two snapshot handoff.
- Placeholder scan: no `TODO`, `TBD`, “implement later”, or unspecified error-handling step remains.
- Type consistency: route payloads and returned status names are defined in the task interfaces; confirmed snapshots are immutable and later tasks consume the exact model IDs returned by earlier tasks.
- Scope: this plan implements only stage one and shared UI. Stage two, three, and four business screens remain separate design tasks as required by the course.
