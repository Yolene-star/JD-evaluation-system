# JD Evaluation System 渐进式改进实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development or executing-plans to implement this plan task-by-task.

**目标：** 在不破坏现有三阶段流程、数据库结构和历史数据的前提下，建立从岗位模型、动态取证到可追溯报告的完整闭环。

**架构：** 保留当前模块化单体架构。数据库和版本化快照是唯一事实源；`assessment_state.py` 负责状态约束，Planner 负责评估目标选择，QuestionTool 负责问题表达，EvidenceTool 负责回答分析，阶段三负责评分和报告。

**技术栈：** Python 3.11+、FastAPI、SQLAlchemy、Pydantic、SQLite/PostgreSQL、React、TypeScript、pytest、Vitest、Playwright、OpenAI 兼容 LLM 接口。

**Spec：** 用户提供的《JD-evaluation-system 总体改进实施计划》及 `AGENTS.md`。

## 全局约束

- 不重写整个 `InterviewAgent`，不删除或绕过 `assessment_state.py`。
- 简历只作为个性化上下文，不进入正式证据和评分。
- 阶段二不得调用评分或报告服务。
- 已确认模型、ResumeSnapshot、Evidence Package、历史报告保持不可变。
- 新字段优先使用 JSON、默认值和可选字段，保持旧 API 与旧快照兼容。
- 所有新行为先写失败测试，再实现。
- 保留工作区已有未提交改动，不覆盖、不回滚、不顺手整理。

## 执行顺序

```text
Phase 1 Evaluation Model
→ Phase 2 Evidence Tool
→ Phase 3 动态出题闭环
→ Phase 5 Stage 3 评分解释
→ Phase 4 Assessment Profile
→ Phase 6 E2E 验证
→ Phase 7 数据库迁移
→ Phase 8 隐私与生命周期
```

每个 Phase 都必须完成：相关规格和实现检查、失败测试、最小实现、阶段测试、全量测试、前端测试/构建、`git diff --check`、影响范围检查和独立提交。

## Phase 1：完善 Evaluation Model 数据链

确保 JD 解析、能力聚合、模型确认和 `ConfirmedModelSnapshot` 始终保留：能力名称、描述、权重、`indicators`、`evidence_requirements`、JD evidence IDs。

实施重点：

- 聚合同名能力时去重合并指标、证据要求和证据 ID；
- 旧快照缺字段时返回空数组；
- 用户补充能力不伪造 JD 来源；
- 确认冻结时完整复制字段；
- 不改变数据库结构和现有 API。

验收：新快照字段完整、旧快照可读、后续 JD 修改不影响旧快照、阶段一到阶段二契约有自动化测试。

## Phase 2：升级 Evidence Tool

扩展回答分析结果：`answer_summary`、`matched_indicators`、`matched_evidence_requirements`、`missing_evidence_requirements`、`evidence_sufficiency`、`needs_follow_up`、`follow_up_reason`。

正式 `EvidenceObservation` 只能引用用户回答中的片段，并绑定具体 `AssessmentTurn`。JD、简历、Prompt 和 LLM 推断只能作为分析上下文或缺口信息，不能直接成为正式证据。

## Phase 3：Evidence-Gap-driven 动态出题

扩展 Planner Decision，增加目标指标、问题策略、问题目标和预期证据。支持 `OPEN_EXPLORATION`、`DETAIL_PROBE`、`TECHNICAL_DEEPEN`、`RESULT_VERIFY`、`SCENARIO_TEST`。

Planner 只选择目标，QuestionTool 负责表达问题，状态机负责轮次、终态和 Session 状态。生成问题前检查历史问题，禁止重复。分析期间前端锁定输入并显示处理中；追问耗尽后进入合法终态，所有能力完成后自动进入阶段三。

## Phase 5：Stage 3 评分解释

建立 `Competency → Indicator → Evidence Requirement → EvidenceObservation → Rubric → Score` 的可追溯链。报告显示可读能力名称、命中指标、缺失指标、回答证据和评分理由；简历背景与面试验证证据分开显示。程序负责评分，AI 只生成受约束解释。

## Phase 4：Assessment Profile

新增可选配置：`assessment_purpose`、`assessment_depth`、`difficulty`、`time_limit`、`interview_style`。旧 Session 默认 `STANDARD`。配置只能改变测评方式和深度，不能改变岗位能力、权重、指标、证据要求和评分规则。Session 创建时冻结配置。

## Phase 6：端到端一致性测试

覆盖 Project、JD、ModelSnapshot、ResumeSnapshot、AssessmentSession、问题、回答、EvidenceObservation、Evidence Package、评分和报告全链路，并验证快照不可变、简历隔离、证据可追溯、Planner 不绕过状态机、重试幂等和失败保留回答。

## Phase 7：数据库迁移治理

盘点启动建表和手动 ALTER，逐步引入 Alembic，提供 upgrade/downgrade，兼容 SQLite/PostgreSQL，并验证事务、幂等、唯一约束、外键、回滚和历史快照。

## Phase 8：隐私与数据生命周期

区分取消当前简历、归档简历和永久删除个人数据；限制原始简历返回；日志不记录完整简历和回答；明确 ResumeContextVersion、ResumeSnapshot 和审计摘要的保留策略。

## 当前执行状态

- Phase 1 已开始；
- 已新增 `backend/tests/test_evaluation_model_contract.py`；
- 聚合逻辑已开始保留并去重 `indicators` 与 `evidence_requirements`；
- 下一步补齐 ConfirmedModelSnapshot 契约测试，再完成 Phase 1 全量验证和独立提交；
- 未经验证不会进入 Phase 2。
