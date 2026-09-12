# JD Evaluation System 三阶段闭环实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立从 JD 解析、动态面试取证到可追溯能力报告的稳定三阶段闭环，并保持历史快照、旧 API 与简历边界不被破坏。

**Architecture:** 保留 FastAPI + SQLAlchemy 模块化单体。阶段一产生不可变 `ConfirmedModelSnapshot`，阶段二只读取该快照并通过 `InterviewAgent/Planner/EvidenceTool` 生成证据包，阶段三由程序执行评分聚合、由 LLM 生成受约束的自然语言解释。数据库快照与服务端状态机是事实源，前端只展示服务端返回状态。

**Tech Stack:** Python 3.11+、FastAPI、SQLAlchemy、Pydantic、SQLite/PostgreSQL、Alembic、React、TypeScript、Vitest、pytest、Playwright、OpenAI 兼容 LLM 接口。

**Spec:** `AGENTS.md`、`docs/superpowers/plans/2026-09-09-full-implementation-roadmap.md`、阶段一/二规格与阶段三报告规格。

## Global Constraints

- 不重写整个 `InterviewAgent`，不删除或绕过 `assessment_state.py`。
- 阶段二不得调用评分或报告服务；简历只作为个性化上下文，不进入正式证据或评分。
- 已确认模型、ResumeSnapshot、Evidence Package 和历史报告保持不可变。
- AI 不得直接写数据库、推进状态机、创建正式能力项、修改权重或计算最终评分。
- 每个新行为先写失败测试，再做最小实现；每个阶段独立验证、提交并记录限制。
- 前端不依赖颜色单独表达状态，服务端响应替换本地快照，支持键盘和窄屏布局。

---

### Task 1: 阶段一 Evaluation Model 数据契约

**Files:**
- Modify: `backend/app/services/aggregation.py`
- Modify: `backend/app/services/assessment_contracts.py`
- Modify: `backend/app/services/stage1_tools.py`
- Test: `backend/tests/test_stage1_invariants.py`
- Create: `backend/tests/test_evaluation_model_contract.py`

**Interfaces:**
- Produces `ConfirmedModelSnapshot.competencies[*]` with `name`, `description`, `weight`, `indicators`, `evidence_requirements`, `jd_evidence_ids`.
- Missing legacy fields deserialize as empty arrays and missing descriptions use a safe empty string.

- [ ] 写测试：同名能力聚合去重合并指标、证据要求和 evidence IDs；旧快照可读取；确认后的快照不受后续 JD 修改影响；用户新增能力没有 JD evidence ID。
- [ ] 运行 `python -m pytest backend/tests/test_evaluation_model_contract.py -q`，确认测试先失败。
- [ ] 实现最小聚合和兼容读取逻辑，不改变表结构和 API 路径。
- [ ] 运行阶段一测试、`python -m pytest backend/tests -q` 与 `git diff --check`。
- [ ] 提交 `feat: preserve evaluation model indicators and evidence requirements`。

### Task 2: 阶段二 EvidenceTool 结构化回答分析

**Files:**
- Modify: `backend/app/services/assessment_ai.py`
- Modify: `backend/app/agent/schemas.py`
- Modify: `backend/app/agent/tools/evidence_tool.py`
- Modify: `backend/app/agent/interview_agent.py`
- Test: `backend/tests/test_assessment_ai_contract.py`
- Create: `backend/tests/test_evidence_gap_analysis.py`

**Interfaces:**
- `AnalysisResult` exposes `answer_summary`, `evidence`, `matched_indicators`, `matched_evidence_requirements`, `missing_evidence_requirements`, `evidence_sufficiency`, `needs_follow_up`, and `follow_up_reason`.
- Only answer-grounded excerpts can become `EvidenceObservation`.

- [ ] 写失败测试覆盖指标命中、证据缺口、旧 LLM JSON 兼容、无效引用、空 JSON、超时和网络失败。
- [ ] 运行目标测试确认失败原因是缺少新契约。
- [ ] 扩展 Schema、Prompt 和兼容转换；对证据片段执行逐字回答校验。
- [ ] 运行 `python -m pytest backend/tests/test_assessment_ai_contract.py backend/tests/test_evidence_gap_analysis.py -q`。
- [ ] 扫描确认简历和 JD Prompt 文本不会写入正式 `EvidenceObservation`。
- [ ] 提交 `feat: add structured evidence gap analysis`。

### Task 3: 阶段二 Planner 与动态出题闭环

**Files:**
- Modify: `backend/app/agent/planner.py`
- Modify: `backend/app/agent/tools/question_tool.py`
- Modify: `backend/app/agent/interview_agent.py`
- Modify: `backend/app/services/assessment_state.py`
- Modify: `frontend/src/components/AssessmentView.tsx`
- Modify: `frontend/src/components/AnswerComposer.tsx`
- Test: `backend/tests/test_agent_planner.py`
- Test: `backend/tests/test_interview_agent.py`
- Test: `frontend/tests/assessment-ui.spec.tsx`

**Interfaces:**
- `PlannerDecision` contains `action`, `target_competency_id`, `target_indicator_ids`, `question_strategy`, `question_goal`, `expected_evidence`, and `reason`.
- Strategies are `OPEN_EXPLORATION`, `DETAIL_PROBE`, `TECHNICAL_DEEPEN`, `RESULT_VERIFY`, `SCENARIO_TEST`.

- [ ] 写失败测试：问题解释目标与缺口、不重复历史问题、追问耗尽进入合法终态、分析期间输入禁用、一次回答后自动显示下一题。
- [ ] 运行相关 pytest/Vitest 确认失败。
- [ ] 让 Planner 只选择正式模型目标；让 QuestionTool 消费策略和缺口；让状态机负责所有转移。
- [ ] 对旧问题重复提交做幂等处理，终态能力不得再次分析。
- [ ] 运行后端阶段二测试、前端测试、构建和 Playwright 阶段二用例。
- [ ] 提交 `feat: complete evidence-gap-driven assessment flow`。

### Task 4: 阶段三评分、报告与咨询 Agent

**Files:**
- Modify: `backend/app/services/scoring.py`
- Modify: `backend/app/services/report_service.py`
- Modify: `backend/app/services/report_chat.py`
- Modify: `backend/app/routes/reports.py`
- Modify: `frontend/src/components/ReportView.tsx`
- Modify: `frontend/src/components/ReportChat.tsx`
- Modify: `frontend/src/types/report.ts`
- Test: `backend/tests/test_stage3_scoring.py`
- Test: `backend/tests/test_stage3_reports.py`
- Test: `backend/tests/test_report_chat.py`
- Test: `frontend/src/components/ReportChat.test.tsx`

**Interfaces:**
- Report evaluations expose readable `matched_indicators`/`missing_indicators` and evidence excerpts while retaining internal IDs for audit.
- Report chat history exposes `cited_evidence` text; UI uses Markdown for the answer body and a separate evidence disclosure card.

- [ ] 写失败测试：报告不显示 UUID；咨询 Agent 不把未评价能力当 0 分；引用可展开看到真实面试原文；Markdown 标题、列表和段落可读。
- [ ] 运行测试确认失败。
- [ ] 用 Confirmed Snapshot 将指标 ID 映射为人类可读名称；用 Session EvidenceObservation 解析历史引用，不返回占位文案。
- [ ] 将正文和面试依据分层显示，保持正文字号不小于用户消息，证据卡不放大整体字号。
- [ ] 运行阶段三后端测试、前端测试和构建。
- [ ] 提交 `feat: make stage three report evidence readable`。

### Task 5: 三阶段端到端验收

**Files:**
- Create/Modify: `backend/tests/test_three_stage_flow.py`
- Create/Modify: `backend/tests/test_resume_assessment_integration.py`
- Modify: `frontend/tests/stage1-real.e2e.ts`
- Modify: `frontend/tests/stage2.spec.ts`
- Modify: `frontend/tests/stage3.spec.ts`

- [ ] 覆盖 Project → JD → ModelSnapshot → AssessmentSession → Answer → EvidencePackage → Report 全链路。
- [ ] 断言修改 JD 不影响旧快照、替换简历不影响旧 ResumeSnapshot、简历不生成证据或评分、重试不重复记录。
- [ ] 运行 `python -m pytest backend/tests -q`、`npm --prefix frontend run test`、`npm --prefix frontend run test:e2e`、`npm --prefix frontend run build`。
- [ ] 提交 `test: verify three-stage assessment invariants`。

### Task 6: Alembic 迁移与隐私治理

**Files:**
- Modify: `backend/alembic/env.py`
- Create: `backend/alembic/versions/<revision>_assessment_profile.py`
- Modify: `backend/requirements.txt`
- Create/Modify: `docs/privacy-and-retention.md`
- Test: `backend/tests/test_migrations.py`
- Test: `backend/tests/test_resume_privacy_contract.py`

- [ ] 为新增字段生成可审查 revision，验证 SQLite/PostgreSQL 的 `upgrade`、`downgrade` 和幂等性；保留旧启动兼容逻辑直到迁移验证完成。
- [ ] 验证普通取消、归档、永久删除语义，日志不记录完整简历和回答，API 不返回原始简历全文。
- [ ] 运行迁移测试、全量后端测试和 `git diff --check`。
- [ ] 提交 `chore: formalize migrations and privacy retention rules`。

## Definition of Done

- 三阶段 API、状态机、快照和报告边界均有自动化测试。
- 阶段二每次回答后服务端返回最新问题、能力状态和 Agent 状态；不需要发送无意义的“继续”。
- 阶段三报告只使用正式测评证据评分，指标、证据和引用对用户可读且可追溯。
- 简历仅用于个性化，不能直接写入证据、能力状态或评分。
- 后端测试、前端测试、E2E、构建和 `git diff --check` 均实际通过。
- 每个阶段独立提交，GitHub 推送前核对暂存文件，绝不带入用户已有无关改动。
