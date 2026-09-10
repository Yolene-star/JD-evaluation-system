# 三阶段评估系统总体实现路线图

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将已完成设计的阶段一 JD 分析、阶段二自适应测评和阶段三能力评价/人才画像实现为一个可联调、可验证、可逐阶段交付的系统。

**Architecture:** 采用 FastAPI + SQLAlchemy 的模块化单体后端和 React + TypeScript 前端，共享 AppShell、项目/事件/证据/版本基础模型。三个阶段通过不可变的数据契约衔接：阶段一输出已确认的岗位胜任力模型快照，阶段二输出版本化测评证据包，阶段三读取证据包生成评分和人才画像。AI 只负责语义理解与叙述，状态机、权限、评分、版本和证据引用由程序控制。

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, SQLAlchemy, SQLite（开发）/PostgreSQL（部署），React, TypeScript, Vite, Vitest, Playwright, pytest。

**Specs:**
- `design/00-全局交互基线设计.md`
- `design/01-阶段一-JD解析与岗位胜任力模型设计.md`
- `docs/superpowers/specs/2026-09-09-stage1-frontend-ui-design.md`
- `docs/superpowers/specs/2026-09-09-stage2-adaptive-assessment-design.md`
- `docs/superpowers/specs/2026-09-09-stage2-frontend-ui-design.md`
- `docs/superpowers/specs/2026-09-09-stage3-capability-evaluation-profile-design.md`
- `docs/superpowers/specs/2026-09-09-stage3-report-ui-design.md`

**Existing detailed plans:**
- 阶段一：`docs/superpowers/plans/2026-09-09-stage1-implementation.md`
- 阶段二：`docs/superpowers/plans/2026-09-09-stage2-adaptive-assessment-implementation.md`

## Global Constraints

- 三阶段复用同一个 AppShell，不为每个阶段开发割裂的页面体系。
- 所有正式结论必须能够回溯到原始材料或测评回答证据。
- 阶段一确认后的模型快照、阶段二完成后的证据包和阶段三报告版本均不可被原地修改。
- 能力权重、状态迁移、评分和权限由程序控制，AI 不得直接写入状态或创建新能力项。
- MVP 先使用确定性演示解析器和 mock/兼容 AI 适配器，保证无 API Key 时仍能跑通流程。
- 每个任务必须先写失败测试，再实现，再运行验证；每个独立任务完成后提交一次。

---

### Task 0: 冻结设计基线与建立实现入口

**Files:**
- Modify: `README.md`
- Create: `docs/architecture/traceability-matrix.md`
- Create: `backend/` and `frontend/` project directories through Task 1

- [ ] **Step 1: 记录当前设计版本**

为每份规格记录当前版本、日期、实现状态和对应实施计划；标记阶段三“有规格、无实施计划”。不在此阶段继续新增交互需求。

- [ ] **Step 2: 建立需求追踪矩阵**

矩阵至少包含：需求编号、来源文档、后端模块、前端组件、自动化测试、验收状态。阶段一和阶段二沿用已有详细计划，阶段三先列出待拆分条目。

- [ ] **Step 3: 统一跨阶段契约**

冻结以下共享对象名称和边界：`Project`、`AuditEvent`、`Evidence`、`ModelVersion`、`ConfirmedModelSnapshot`、`AssessmentEvidencePackage`、`ProfileReportVersion`。任何阶段不得通过前端临时字段绕过这些契约。

- [ ] **Step 4: 验证设计文档一致性**

检查阶段编号、状态枚举、版本命名、接口路径和 UI 文案是否冲突；把决定写入追踪矩阵，而不是边编码边改变规则。

**验收：** 设计文档有明确基线；后续开发知道每个接口和页面对应哪个需求；没有未决的跨阶段命名冲突。

### Task 1: 建立共享后端、前端和测试骨架

**Files:** 由阶段一详细计划 Task 1 定义的 `backend/app/*`、`backend/tests/test_health.py`、`frontend/*`。

- [ ] **Step 1:** 按阶段一计划先写并运行健康检查失败测试。
- [ ] **Step 2:** 创建 FastAPI、SQLAlchemy、Pydantic、SQLite 测试数据库和共享领域模型。
- [ ] **Step 3:** 创建 React/Vite/TypeScript AppShell、设计令牌和 API 客户端。
- [ ] **Step 4:** 运行 `python -m pytest backend/tests -q` 与 `npm --prefix frontend run build`。

**验收：** `/api/health` 返回 `{"status":"ok"}`；前端能构建；三栏外壳能显示占位数据。

### Task 2: 完成阶段一 JD 分析闭环

**Plan:** 严格执行 `2026-09-09-stage1-implementation.md` 的 Task 2–6。

- [ ] **Step 1:** 实现项目、历史任务、四种 JD 入口和审计事件。
- [ ] **Step 2:** 实现确定性解析、证据片段、单份 JD 模型和失败重试。
- [ ] **Step 3:** 实现总模型聚合、冲突处理、草稿编辑、移出/重新加入。
- [ ] **Step 4:** 实现确认、不可变 `v1.0` 快照、导出和完成页。
- [ ] **Step 5:** 运行阶段一后端不变量测试、前端构建和 Playwright 流程。

**验收：** 两份文本 JD 可以完成“添加 → 解析 → 查看证据 → 处理冲突 → 确认冻结 → 导出”；正式能力项证据覆盖率 100%，能力权重和为 100%。

### Task 3: 固化阶段一到阶段二的交接

**Files:** `backend/app/services/assessment_contracts.py`、阶段二测试夹具、共享 API 类型文件。

- [ ] **Step 1:** 用已确认的阶段一模型创建 `ConfirmedModelSnapshot` 测试夹具。
- [ ] **Step 2:** 验证草稿模型、未确认模型和已确认模型的读取边界。
- [ ] **Step 3:** 固定快照中能力顺序、权重、JD 证据引用和版本号字段。
- [ ] **Step 4:** 在前端 API 类型中使用同一字段名，禁止阶段二重新解释阶段一数据。

**验收：** 阶段二只能读取确认快照，不能修改阶段一模型；快照测试稳定通过。

### Task 4: 完成阶段二自适应测评闭环

**Plan:** 执行 `2026-09-09-stage2-adaptive-assessment-implementation.md` 的 Task 1–7。

- [ ] **Step 1:** 建立测评会话、能力测评项、轮次、观察证据和事件模型。
- [ ] **Step 2:** 实现 READY/IN_PROGRESS/PAUSED/COMPLETED 等状态机和幂等提交。
- [ ] **Step 3:** 实现结构化问题生成、回答分析、证据校验和有限重试。
- [ ] **Step 4:** 实现会话/轮次 API、暂停恢复、提前结束和事件查询。
- [ ] **Step 5:** 导出版本化 `AssessmentEvidencePackage`。
- [ ] **Step 6:** 实现桌面端与窄屏测评工作台、处理中/失败/恢复/完成状态。
- [ ] **Step 7:** 运行恢复场景、重复提交、综合题和浏览器端到端测试。

**验收：** 用户能开始、回答、追问、暂停、恢复和完成测评；重复请求不产生重复轮次；阶段二不计算正式分数。

### Task 5: 为阶段三补齐实施计划并实现评分服务

**Files:**
- Create: `docs/superpowers/plans/2026-09-09-stage3-implementation.md`
- Create/Modify: `backend/app/services/scoring.py`, `backend/app/services/profile.py`, `backend/app/routes/reports.py`
- Create: `backend/tests/test_stage3_scoring.py`

- [ ] **Step 1: 从阶段三规格拆出数据流和 API 任务**

明确输入只允许来自版本化 `AssessmentEvidencePackage`，输出包含能力状态、五档 Rubric 结论、达成度、岗位匹配度、解释文本和证据引用。

- [ ] **Step 2: 先写评分不变量测试**

覆盖五档 Rubric 边界、缺失证据、不确定证据、能力权重归一化、匹配度计算和报告版本不可变性。

- [ ] **Step 3: 实现确定性评分核心**

将 AI 输出转换为受校验的中间结构，由程序计算正式分数、状态和聚合指标；缺证据时返回待补充而不是猜测。

- [ ] **Step 4: 实现报告 API 和版本操作**

支持生成报告、读取概览/矩阵/优势短板/发展建议、查看证据抽屉、创建重新计算版本；旧报告只读。

**验收：** 同一证据包重复计算得到一致结果；任何报告结论都能回溯证据；旧版本不会被覆盖。

### Task 6: 完成阶段三人才画像报告 UI

**Files:** 依据 `2026-09-09-stage3-report-ui-design.md` 创建报告页、指标区、能力矩阵、证据抽屉和移动布局组件。

- [ ] **Step 1:** 复用 AppShell 和阶段导航，接入阶段三 API 类型。
- [ ] **Step 2:** 实现概览指标、能力评价矩阵、优势/短板/发展建议区。
- [ ] **Step 3:** 实现证据抽屉、版本切换、重新计算和空/异常状态。
- [ ] **Step 4:** 添加组件测试、响应式测试和报告浏览器流程测试。

**验收：** 报告在桌面和窄屏均可阅读；用户可以从结论回到原始测评证据；未完成测评时不会显示虚假的完整报告。

### Task 7: 全链路验收、质量中心和部署准备

**Files:** `backend/tests/`、`frontend/tests/`、`README.md`、质量评估相关模块。

- [ ] **Step 1:** 编写跨阶段浏览器流程：阶段一确认 → 阶段二测评 → 阶段三报告。
- [ ] **Step 2:** 加入复杂多轮、恶意文本、失败重试、并发修改、撤销和版本回溯测试。
- [ ] **Step 3:** 运行后端全量测试、前端构建、Playwright、`git diff --check`。
- [ ] **Step 4:** 补充环境变量、演示解析器、数据库迁移、启动和故障排查文档。
- [ ] **Step 5:** 只有核心流程稳定后，再实现阶段四质量评估/持续优化功能。

**验收：** 三阶段核心流程可重复演示；关键不变量和恢复路径有自动化证据；文档中的启动命令与实际工程一致。

## Recommended Execution Order

1. Task 0–1：共享契约和工程骨架。
2. Task 2：完整交付阶段一，作为第一个可用版本。
3. Task 3–4：完成阶段二并冻结证据包契约。
4. Task 5–6：完成阶段三评分和报告。
5. Task 7：全链路验证，再考虑阶段四。

## Parallel Work Boundaries

- 后端可并行：领域模型/API/服务/测试；前端可并行：AppShell/组件/mock 数据/组件测试。
- 前后端只在 API 契约冻结后联调；接口字段变更必须同步更新 Pydantic schema、TypeScript 类型和契约测试。
- 阶段二不能在阶段一确认快照契约稳定前开始业务实现；阶段三不能在阶段二证据包契约稳定前开始正式评分。

## First Implementation Session

第一轮只做以下内容：

1. 保护并确认当前设计文档版本。
2. 执行阶段一实施计划 Task 1：后端健康检查、共享模型、前端 AppShell。
3. 让后端测试和前端生产构建都通过。
4. 再进入阶段一的 JD 创建与材料录入，不提前实现阶段二/三业务。
