# 阶段三能力评价与人才画像实施计划

## 目标与边界

阶段三读取阶段二 `FULL` 或 `PARTIAL` 证据包，生成不可变、可追溯的评分报告。程序决定 Rubric、能力分数、达成度、权重归一化、匹配度和版本状态；AI 仅生成受约束的叙述。不得修改阶段一模型、阶段二回答/观察或历史报告，不得将未完成能力项当作 0 分。

## Task 1：评分领域模型与 Rubric 快照

文件：`backend/app/models.py`、`backend/app/schemas.py`、`backend/app/services/rubrics.py`、`backend/tests/test_stage3_models.py`。

先写失败测试，覆盖 RubricSet/CompetencyRubric/AssessmentReport/CompetencyEvaluation/ReportNarrative、DRAFT/ACTIVE/RETIRED、报告版本和不可变引用。实现默认 Rubric 生成、激活校验、能力项覆盖校验、评分规则版本字段及 SQLite additive migration。激活后的 Rubric 不允许原地修改。

## Task 2：确定性评分与匹配度

文件：`backend/app/services/scoring.py`、`backend/tests/test_stage3_scoring.py`。

先写失败测试，覆盖 POSITIVE/NEGATIVE/MISSING/UNCERTAIN 组合、0-2/3-4/5-6/7-8/9-10 档位边界、档位内负向扣分、`SUFFICIENT`/`EXHAUSTED`/`INCOMPLETE`、置信度、FULL 匹配度、PARTIAL 权重重新归一化、全未评价返回 null。实现纯函数评分核心，输入只能是版本化证据包与 ACTIVE Rubric，输出保存所有证据和指标引用。

## Task 3：报告生成服务与叙述适配器

文件：`backend/app/services/report_service.py`、`backend/app/services/profile.py`、`backend/app/services/profile_prompts.py`、`backend/tests/test_stage3_reports.py`。

先写失败测试，覆盖同一幂等键返回既有报告、重新计算创建新版本、评分成功但 AI 叙述失败仍保留基础报告、无效能力/证据引用降级为 `PENDING_RETRY`。实现证据包版本、模型版本、Rubric 版本、评分规则版本快照；叙述输入只传结构化评分事实，禁止让 AI 改分数/匹配度或对 INCOMPLETE 下确定性结论。

## Task 4：报告、Rubric 与评分规则 API

文件：`backend/app/routes/reports.py`、`backend/app/routes/rubrics.py`、`backend/app/main.py`、`backend/tests/test_stage3_api.py`。

实现：

- `POST /api/assessment-sessions/{session_id}/reports`
- `GET /api/assessment-sessions/{session_id}/reports`
- `GET /api/reports/{report_id}`
- `POST /api/reports/{report_id}/narrative/retry`
- `GET /api/reports/{report_id}/scoring-policy`
- `GET/POST /api/model-versions/{model_version_id}/rubrics`
- `GET /api/rubric-sets/{rubric_set_id}`
- `POST /api/rubric-sets/{rubric_set_id}/activate`

API 必须校验会话归属、终态证据包、模型版本一致性、ACTIVE Rubric、幂等键和资源状态；错误使用稳定状态码/错误码。报告详情返回概览、矩阵、证据引用、叙述状态和版本信息，但不允许覆盖旧版本。

## Task 5：同一 AppShell 的阶段三报告 UI

文件：`frontend/src/types/report.ts`、`frontend/src/lib/api.ts`、报告组件、`frontend/src/app/App.tsx`、`frontend/src/app/app.css`、`frontend/tests/report-ui.spec.tsx`。

先写失败组件测试。实现阶段三入口和报告页，复用阶段一/二外壳；提供 FULL/PARTIAL 提示、匹配度、覆盖度、能力矩阵、证据抽屉、优势/短板/建议、版本选择、评分规则和重新计算。`INCOMPLETE` 显示“不可完全评价”，不显示 0 分；雷达图只绘制已评分能力并提供文本/表格替代。支持移动纵向布局、键盘焦点、Escape、44px 触控和 reduced-motion。

## Task 6：跨阶段验收与文档

文件：`backend/tests/test_stage3_invariants.py`、`frontend/tests/stage3.spec.ts`、`README.md`、阶段三规格。

覆盖阶段一确认 → 阶段二证据包 → 阶段三报告、部分报告、AI 叙述失败重试、重复生成、历史版本和无评分字段错误。更新启动、API、DeepSeek/mock、评分政策及阶段四未实现说明。运行完整后端测试、Vitest、Playwright、生产构建和 `git diff --check`。

## 约束

- 不提交真实 API Key，不创建或修改招聘数据爬虫。
- 不计算或展示超出阶段三规格的招聘决策结论。
- 保留当前工作区用户改动；不执行回滚、清理或 Git commit。
