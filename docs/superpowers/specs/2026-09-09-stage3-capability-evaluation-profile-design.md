# 阶段三：能力评价与人才画像设计规格

## 1. 目标与范围

阶段三读取阶段二生成的版本化 `FULL` 或 `PARTIAL` 证据包，将逐能力项证据转换为可追溯的能力评分、能力达成度、岗位匹配度和人才画像报告。

本阶段采用“规则主导评分、AI 受约束叙述”的架构：程序决定能力状态、分数、达成度和匹配度；AI 只基于程序提供的结构化事实生成综合评价、优势、短板和发展建议。阶段三不修改阶段一模型、阶段二原始回答、阶段二证据观察或历史报告。

结果仅是实验系统内部的辅助性测评结果，不构成正式招聘决策、心理测量、职业资格认证或录用建议。

## 2. 已确认的设计决策

- 采用规则主导型评分，不让 AI 直接决定分数。
- 每个能力项拥有独立、版本化、可激活的专属 Rubric。
- `INCOMPLETE` 不等于 0 分；其 `score` 和 `attainment` 均为 `null`。
- `FULL` 报告要求所有能力项进入可评分终态；`PARTIAL` 报告允许存在未完成能力项。
- 部分岗位匹配度只使用已评价能力项，并按已评价权重重新归一化。
- Rubric、证据包和报告均不可覆盖；重新计算创建新版本。
- AI 叙述失败不影响基础评分报告，允许单独重试叙述生成。
- 首版聚焦“一个证据包生成一个报告”的闭环，不包含复杂人工复核工作流。

## 3. 领域模型

```text
EvidencePackage
- id
- assessment_session_id
- model_version_id
- package_version
- completion: FULL | PARTIAL
- generated_at
- competency_observations[]

RubricSet
- id
- model_version_id
- version
- status: DRAFT | ACTIVE | RETIRED
- competencies[]

CompetencyRubric
- competency_id
- rubric_version
- level_0_2
- level_3_4
- level_5_6
- level_7_8
- level_9_10
- indicators[]
- scoring_rules[]

CompetencyEvaluation
- competency_id
- status: SCORED | INCOMPLETE
- score: 0..10 | null
- attainment: 0..1 | null
- level
- evidence_ids[]
- matched_indicator_ids[]
- negative_evidence_ids[]
- missing_indicator_ids[]
- confidence
- rationale

AssessmentReport
- id
- assessment_session_id
- report_version
- evidence_package_id
- model_version_id
- rubric_set_id
- scoring_rule_version
- completion: FULL | PARTIAL
- evaluated_weight
- unevaluated_weight
- match_score: 0..100 | null
- match_score_type: FULL | PARTIAL | NONE
- status: GENERATING | READY | FAILED
- narrative_status: PENDING | GENERATING | READY | PENDING_RETRY | FAILED
- created_at

ReportNarrative
- report_id
- overview
- strengths[]
- weaknesses[]
- recommendations[]
- cited_evidence_ids[]
```

`EvidencePackage`、`RubricSet` 和 `AssessmentReport` 都是不可变快照。阶段三通过引用证据 ID 追溯阶段二原文，不复制或改写原始证据。

## 4. 评分规则

### 4.1 能力状态

```text
SUFFICIENT → 可评分
EXHAUSTED  → 可评分，通常进入较低档位
INCOMPLETE → 不评分，score = null
```

### 4.2 五档专属 Rubric

每个能力项根据阶段一的名称、描述和 JD 证据建立具体指标。通用档位如下，能力专属 Rubric 必须补充可验证的指标和边界：

```text
0–2：无有效正向证据，或存在严重反向证据
3–4：只有零散理解，主要指标未覆盖
5–6：覆盖基础指标，可完成常规任务
7–8：覆盖主要指标，可处理常规及部分复杂场景
9–10：覆盖全部核心指标，并能说明权衡、边界和实践经验
```

证据映射规则：

- `POSITIVE` 命中或部分命中指标；
- `NEGATIVE` 产生明确反向证据；
- `MISSING` 表示要求涉及但回答未覆盖；
- `UNCERTAIN` 不直接加分或扣分，只降低置信度。

程序依据指标覆盖比例和负向证据选择档位。同一档位内使用确定性规则取具体分数，例如 7–8 档中核心指标覆盖率达到 75% 取 8 分，50%–74% 取 7 分。负向证据可以在档位内扣 1 分，但不能突破档位边界。

每项评分必须保存：

```text
score
score_level
matched_indicator_ids
negative_evidence_ids
missing_indicator_ids
evidence_ids
confidence
rationale
```

### 4.3 达成度和岗位匹配度

```text
attainment = score / 10
```

权重统一归一化到 `0..1`。完整报告：

```text
match_score = Σ(score_i × weight_i) / Σ(evaluated weights) / 10 × 100
```

部分报告仅纳入已评价能力项：

```text
evaluated_weight = Σ(weight_i where status != INCOMPLETE)
partial_match_score = Σ(score_i × weight_i) / evaluated_weight / 10 × 100
```

部分报告同时展示 `evaluated_weight`、`unevaluated_weight` 和 `match_score_type = PARTIAL`。若 `evaluated_weight = 0`，匹配度为 `null`。分数展示保留一位小数，结果必须限制在 `0..100`。

## 5. 数据流

```text
读取 EvidencePackage
  → 校验模型版本和 RubricSet
  → 按 competency_id 聚合证据
  → 判断能力状态
  → 匹配专属 Rubric 指标
  → 计算能力分数、达成度和置信度
  → 按已评价权重计算匹配度
  → 保存不可变基础报告
  → 将结构化摘要交给 AI
  → 校验叙述引用
  → 保存叙述或标记待重试
```

报告生成必须保存证据包版本、胜任力模型版本、Rubric 版本和评分规则版本，以支持复算和阶段四的版本比较。

## 6. AI 叙述合约

AI 只接收岗位名称、完成类型、能力分数、达成度、Rubric 档位、证据摘要、未完成能力项和匹配度等结构化信息，不接收不必要的完整原始对话。

返回结构：

```json
{
  "overview": {"text": "...", "evidence_ids": ["e1"]},
  "strengths": [{"competency_id": "c1", "text": "...", "evidence_ids": ["e1"]}],
  "weaknesses": [{"competency_id": "c2", "text": "...", "evidence_ids": ["e5"]}],
  "recommendations": [{"competency_id": "c2", "text": "...", "evidence_ids": ["e5", "e6"]}]
}
```

程序必须拒绝或降级不存在的能力/证据引用、修改分数或匹配度、对 `INCOMPLETE` 作确定性结论、无证据结论、空字段、重复建议和招聘决策式表述。校验失败时保留基础报告，设置 `narrative_status = PENDING_RETRY`，不回滚确定性评分。

## 7. API 契约

```text
POST /api/assessment-sessions/{session_id}/reports
GET  /api/assessment-sessions/{session_id}/reports
GET  /api/reports/{report_id}
POST /api/reports/{report_id}/narrative/retry

GET  /api/model-versions/{model_version_id}/rubrics
POST /api/model-versions/{model_version_id}/rubrics
GET  /api/rubric-sets/{rubric_set_id}
POST /api/rubric-sets/{rubric_set_id}/activate
```

生成报告请求：

```json
{
  "evidence_package_id": "ep_123",
  "rubric_set_id": "rs_2",
  "idempotency_key": "client-generated-key"
}
```

相同会话、证据包、Rubric、评分规则版本和幂等键只创建一份报告；重新计算必须使用新的幂等键并创建新报告版本。已激活 Rubric 不允许原地编辑。

## 8. 报告页面

报告页面包含：

1. 结果概览：岗位、报告版本、完整/部分结果、匹配度、已评价权重和生成时间。
2. 能力评价矩阵：分数、达成度、状态、Rubric 档位、置信度和证据数量；未完成项显示“不可完全评价”。
3. 证据详情：按正向、负向、缺失、不确定类型展示原文、轮次和证据 ID。
4. 人才画像叙述：综合评价、优势、短板和建议，并可定位引用证据。
5. 可视化和版本信息：雷达图、柱状图、模型/Rubric/评分规则/报告版本。

雷达图只绘制已评分能力；未完成项不绘制为 0 分，部分报告必须标注“部分结果”，并同时提供表格。

## 9. 异常与事件

证据包不存在、模型版本冲突、无激活 Rubric、缺少能力 Rubric、证据引用失效、权重非法或总权重为零时，确定性评分失败并记录原因。AI 超时或 Schema 错误只影响叙述状态，基础报告仍可用。重复请求返回既有结果。

建议事件：

```text
REPORT_GENERATION_REQUESTED
EVIDENCE_PACKAGE_VALIDATED
RUBRIC_SET_VALIDATED
COMPETENCY_SCORED
COMPETENCY_MARKED_INCOMPLETE
MATCH_SCORE_CALCULATED
REPORT_READY
REPORT_GENERATION_FAILED
NARRATIVE_GENERATION_REQUESTED
NARRATIVE_READY
NARRATIVE_INVALID_RESPONSE
NARRATIVE_RETRY_REQUESTED
```

## 10. 测试与验收

后端测试覆盖 Rubric 边界、证据类型组合、三种能力状态、档位内扣分、权重归一化、完整/部分匹配度、全未评价、幂等性、Rubric/报告不可变性和 AI 引用校验。

前端测试覆盖完整/部分标识、未完成项不显示为 0、雷达图与表格一致、证据抽屉定位原文、历史报告、重新计算不覆盖旧版本、AI 失败后的基础报告和键盘/窄屏可用性。

演示必须跑通：

```text
完成或提前结束阶段二
→ 获取 FULL/PARTIAL 证据包
→ 选择已激活 Rubric
→ 生成报告
→ 查看评分、证据、匹配度和雷达图
→ 查看优势、短板和建议
→ 重试叙述
→ 激活新版 Rubric 后重新计算
→ 旧报告仍可查看
```

## 11. 首版不做

- 自动招聘、录用、淘汰、排名或正式职业资格判断；
- AI 自由修改分数或临时修改 Rubric；
- 将未完成能力项计为 0 分；
- 多人协同编辑和复杂人工复核工作流；
- 跨候选人横向比较；
- 自动抓取招聘网站数据；
- 语音、视频或代码执行测评。
