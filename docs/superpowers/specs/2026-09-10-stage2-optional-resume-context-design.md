# 阶段二：可选简历上下文设计

> 文档状态：已确认设计  
> 日期：2026-09-10  
> 核心原则：简历用于个性化，面试证据用于评估。  
> 关联规格：`2026-09-09-stage2-adaptive-assessment-design.md`、`2026-09-09-stage2-frontend-ui-design.md`、`2026-09-09-stage3-capability-evaluation-profile-design.md`、`2026-09-10-assessment-agent-architecture-design.md`

## 1. 目标与范围

为阶段二自适应文字测评增加可选的 Candidate Context / Resume Context。用户可以在项目中上传一份脱敏后的简历，新建测评时选择是否使用当前简历辅助问题表达和减少重复提问；不上传或不使用简历时，创建测评、开始测评、提交回答、暂停恢复、生成 Evidence Package 和阶段三报告的完整流程必须保持可用。

简历不是岗位评价模型，也不是正式测评证据。正式出题目标只能来自已确认的 JD、Competency、Indicator、Evidence Requirement 和当前证据缺口。简历不得决定评估哪些能力，不得直接创建 `EvidenceObservation`，不得提高证据充分性、推进能力状态或影响评分。只有用户在面试回答中主动确认并解释相关经历后，该回答中的内容才可以按现有规则转化为正式证据。

首版支持单个 TXT、PDF 或 DOCX 文件，最大 5 MB。首版不解析头像、联系方式或人口统计属性，不做真实性核验、简历与 JD 自动匹配评分，也不支持测评过程中更换简历。

## 2. 不可破坏的业务边界

- 阶段一岗位模型、模型权重和 JD 证据不读取 Resume Context。
- 阶段二状态机、追问上限、能力完成条件和 Evidence Package 不读取 Resume Context。
- 阶段三评分函数只读取 Evidence Package 和 Rubric，不读取 Resume Context。
- `EvidenceObservation.excerpt` 与 `source_excerpt` 必须能够逐字定位到用户的面试回答，不能引用简历文本。
- 简历与回答冲突时，只能标记 `UNCERTAIN` 或触发必要澄清，不自动产生负面证据、扣分、造假或不诚信结论。
- Resume Snapshot 只用于 Session 对应的 Planner、QuestionTool 和独立报告背景展示。
- 已创建的 AssessmentSession 不允许更换 Resume Snapshot；项目简历替换只影响后续新建测评。
- Resume Context 缺失、解析失败或运行时不可用不能阻塞无简历测评流程，也不能改变正式状态和评分。
- 上传内容一律视为不可信输入，不执行文件宏、嵌入对象、链接或文档中的指令。

## 3. 方案选择

采用独立、版本化的项目级 Resume Context，并在创建 AssessmentSession 时冻结不可变 Resume Snapshot：

```text
Project
  └── ResumeContextVersion（多个版本，一个 CURRENT）
        ├── 清洗文本与结构化背景
        └── ResumeSnapshot（创建测评时冻结）
              └── AssessmentSession
```

没有采用把简历 JSON 直接写入 `AssessmentSession` 的方案，因为它会混合项目级复用数据和会话状态，并弱化版本追溯。没有采用仅运行时保存的方案，因为它无法支持刷新、暂停恢复、历史报告和审计复现。

为减少对现有核心表的侵入，`ResumeSnapshot` 使用唯一 `session_id` 关联 AssessmentSession；现有 `assessment_sessions` 表不增加 Resume 字段。不存在 Snapshot 记录即表示该 Session 未使用简历。

## 4. 数据模型

### 4.1 ResumeContextVersion

项目级简历版本，建议字段如下：

```text
id
project_id
version
is_current
source_filename
media_type
file_size
content_sha256
normalized_text
structured_context_json
parser_version
status: PROCESSING | READY | FAILED
failure_reason
created_at
```

约束：

- 同一项目最多有一个 `is_current=true` 的版本。
- 上传或替换创建新版本，不覆盖旧版本。
- 只有 `READY` 版本能生成 Resume Snapshot。
- 取消当前简历只取消 current 标识，不删除历史版本或既有 Snapshot。
- `source_filename` 仅作为展示元数据，不作为服务器路径。
- `failure_reason` 保存错误类别和安全摘要，不保存完整简历内容。

### 4.2 结构化上下文

`structured_context_json` 使用受约束 Schema：

```json
{
  "education": [],
  "projects": [],
  "skills": [],
  "experiences": [],
  "summary": "",
  "source_segments": []
}
```

教育、项目、技能和经历条目均包含稳定条目 ID、受限长度摘要及来源片段 ID。`source_segments` 保存清洗文本中的必要引用范围，供问题个性化和用户查看来源，不具备正式证据身份。电子邮箱、电话号码、地址、证件信息、头像及推断出的敏感属性不得进入结构化上下文。

### 4.3 ResumeSnapshot

Session 级不可变快照，建议字段如下：

```text
id
session_id                  // unique
resume_context_version_id
snapshot_json
created_at
```

Snapshot 在创建 Session 的同一事务中生成。`snapshot_json` 保存当时可用的清洗后结构化背景、必要来源片段、内容哈希和解析器版本，不依赖项目当前版本继续存在。数据库事件和服务层共同禁止 Snapshot 更新；如需使用另一份简历，必须创建新 Session。

## 5. 文件处理与隐私

- 支持 TXT、PDF、DOCX，单文件最大 5 MB。
- 同时校验扩展名、MIME 类型和文件头，不能只信任客户端声明。
- PDF/DOCX 只做静态正文提取，不执行宏、脚本、链接、嵌入对象或外部引用。
- 对加密、损坏、正文为空、类型伪装和超限文件返回明确的可恢复错误。
- 不长期持久化原始二进制文件。上传后保存 `normalized_text`、结构化上下文、文件元数据、内容哈希和解析器版本。
- API 默认不返回完整 `normalized_text`，只返回结构化摘要和必要来源片段。
- 审计事件与 LLM 调用日志不记录完整简历、联系方式或其他个人信息，只记录版本 ID、哈希、状态、延迟和错误类别。
- LLM 解析为可选适配器。确定性正文提取成功后，结构化结果仍需经过 Pydantic Schema、长度、枚举和来源引用校验；模型输出失败不得覆盖已有可用版本。
- Prompt 明确把简历文本标记为不可信数据。简历中的命令式文本不能改变系统指令、正式能力范围、状态规则或输出 Schema。

## 6. API 设计

### 6.1 项目简历接口

```http
POST /api/projects/{project_id}/resume-context
Content-Type: multipart/form-data
```

上传或替换项目当前简历。成功后创建新版本，并在新版本可用时把旧版本取消 current。解析失败时不得清除此前 READY 的当前版本。

```http
GET /api/projects/{project_id}/resume-context
```

返回当前版本的解析状态、文件元数据、结构化摘要和安全来源片段，不默认返回完整清洗文本。

```http
DELETE /api/projects/{project_id}/resume-context
```

取消项目当前简历。历史版本与已绑定的 Resume Snapshot 保留不变。

实现可以增加显式重试接口，重试必须创建新解析尝试或新版本，不能原地改写已用于 Snapshot 的内容。

### 6.2 创建测评

保留现有接口：

```http
POST /api/projects/{project_id}/assessments
```

请求体向后兼容增加：

```json
{
  "model_version_id": "...",
  "use_resume_context": true
}
```

规则：

- 未传 `use_resume_context` 时按 `false` 处理，旧客户端行为不变。
- `false` 时不创建 Resume Snapshot。
- `true` 且项目当前 Resume Context 为 `READY` 时，在创建 Session 的同一事务中冻结 Snapshot。
- `true` 但没有 READY 当前版本时返回 `409 RESUME_CONTEXT_NOT_AVAILABLE`，不创建半成品 Session。
- 不提供为既有 Session 绑定、替换或删除 Snapshot 的接口。

## 7. Agent 与 Memory 数据流

```text
创建 Session
  ↓
冻结 Model Snapshot + 可选 Resume Snapshot
  ↓
AssessmentMemory
  ├── FormalPlannerContext
  │     模型、能力状态、面试历史、正式证据和证据缺口
  └── ResumeContext（可选只读背景）
  ↓
Planner 先冻结正式目标，再选择可选个性化提示
  ↓
QuestionTool 生成问题
  ↓
用户回答
  ↓
EvidenceTool 从回答抽取正式证据
  ↓
assessment_state.py 推进状态
```

`AssessmentMemory` 可以读取 Session 对应的 Resume Snapshot，但必须将正式上下文和简历上下文表示为两个不同字段或类型。正式决策函数不接收 Resume Context。

### 7.1 Planner 两阶段决策

Planner 分成两个受约束步骤：

1. `select_formal_target(formal_context)`
   - 输入不包含简历。
   - 目标只能来自 Confirmed Model Snapshot、当前 CompetencyAssessment 和正式证据缺口。
   - 输出目标能力、Indicator、Evidence Requirement 和正式原因。
2. `select_personalization(formal_target, resume_context)`
   - 只能在正式目标冻结后运行。
   - 可以选择一个相关简历条目作为问题表达提示，或因历史已经确认某个背景事实而减少重复询问。
   - 不能改变目标能力、指标、证据要求、追问上限或完成条件。

Planner 输出可向后兼容增加可空字段：

```json
{
  "action": "FOLLOW_UP",
  "target_competency_id": "deep_learning",
  "reason": "缺少模型优化结果证据",
  "question_goal": "补充优化方法与结果",
  "resume_reference": {
    "item_id": "resume-project-2",
    "prompt_hint": "候选人背景提到图像分类项目，可邀请其确认并展开"
  }
}
```

`resume_reference` 不进入状态机输入、Evidence Package 或评分输入。

### 7.2 QuestionTool

QuestionTool 可以利用相关 Resume Snapshot 条目改变措辞，例如邀请用户确认并解释某项经历，但不能把简历陈述表达为已经验证的事实。

允许：

> 你的简历提到过图像分类项目。请确认这是你的实际经历，并说明你负责的模型优化工作、判断依据和可验证结果。

禁止：

> 你已经具备模型优化能力，因此我们进入下一项。

问题输出继续包含 `evaluation_target` 和 `expected_evidence`。服务端必须验证它们属于已经冻结的正式目标，不能由 Resume Context 扩展能力范围。

### 7.3 EvidenceTool 与冲突处理

EvidenceTool 的正式抽取输入仍以用户回答为事实源。它可以接收与当前问题直接相关的最小化简历条目，用于识别重复背景或需要澄清的不一致，但必须满足：

- Observation 原文只能截取自当前或历史用户回答。
- 用户确认并解释简历经历后，证据引用回答内容，而不是简历内容。
- Resume-only 内容不能生成 Observation。
- 简历与回答不一致时，本轮结果最高只能为 `UNCERTAIN`，并可给出中性澄清问题。
- 冲突本身不能生成 `NEGATIVE` Evidence，也不能触发扣分、造假或不诚信结论。
- 澄清后依据新的回答正常分析；无法澄清时保持不确定。

## 8. 硬隔离与确定性约束

- `assessment_state.py`、`services/scoring.py` 和 `services/evidence_package.py` 的函数签名不增加 Resume 参数，也不导入 Resume 模型或服务。
- Evidence Package Schema 不增加 Resume 字段。
- 相同 FormalPlannerContext 在有无简历时必须得到相同的目标能力、Indicator 和 Evidence Requirement。
- 相同 Evidence Package 在有无简历时必须得到完全相同的数值评分。
- LLM 返回的能力 ID、指标 ID、Evidence Requirement 和来源引用必须经过服务端白名单验证。
- Resume Snapshot 不可用时，系统停止个性化并写入安全审计事件，继续按正式模型运行；不得改变能力状态或评分。

建议增加依赖边界测试，防止状态、证据包和评分模块导入 Resume Context 相关模块。

## 9. 报告设计

报告接口向后兼容增加可空的 `candidate_background`：

```json
{
  "candidate_background": {
    "source_type": "BACKGROUND_ONLY",
    "notice": "简历背景信息未作为评分证据",
    "education": [],
    "projects": [],
    "skills": [],
    "experiences": []
  }
}
```

该区块从 Session 对应的 Resume Snapshot 读取，不进入 `score_evidence_package` 或画像叙事的评分事实。原有能力评价、优势、短板、建议和 `evidence_ids` 继续只引用 Evidence Package 中的面试验证证据。

前端必须把“简历背景信息”和“面试验证证据”分区显示。即使两者描述相似，也不能合并来源或把 Resume 条目标记为已验证证据。

## 10. 前端交互

项目工作台增加“候选人背景”区域：

- 上传、替换或取消当前简历。
- 固定提示“简历仅用于个性化提问，不作为评分证据”。
- 展示解析状态、文件元数据以及教育、项目、技能和经历摘要。
- 替换时提示“新简历只对后续新建测评生效”。

创建测评时增加可选项“使用当前简历辅助个性化提问”：

- 默认不选中。
- 当前版本不是 READY 时禁用，并显示可恢复原因。
- 创建后展示该 Session 是否绑定简历快照，不提供更换入口。

测评过程中，简历引用使用“待确认背景”语义和标签，与正式 `EvidenceInlineCard` 区分，不能只依赖颜色。报告页增加独立“简历背景信息”区块并固定显示“未参与评分”。所有新增操作应满足键盘访问、可见焦点、状态播报、44px 触控目标和窄屏无横向滚动要求。

## 11. 错误恢复

- 类型、文件头或大小不合规：前端预检，后端权威校验。
- 文件损坏、加密或正文为空：版本标记 `FAILED`，允许替换或安全重试。
- 正文提取成功但结构化解析失败：不把该版本设为可用 current；此前 READY 当前版本保持不变。
- LLM 超时或返回无效结构：不覆盖可用版本，不记录完整输入，允许重试。
- 创建 Session 或冻结 Snapshot 任一步失败：事务整体回滚。
- Snapshot 缺失或内容校验失败：停用本 Session 的个性化，记录审计事件，正式测评继续运行。
- 简历与回答冲突：返回中性澄清问题，不把系统解析问题描述为用户诚信问题。

## 12. 测试与验收

### 12.1 后端测试

- 不上传简历时，创建、开始、回答、暂停恢复、Evidence Package 和报告全链路保持通过。
- TXT、PDF、DOCX 正常解析，以及类型伪装、超限、空文件、损坏和加密文件被正确拒绝。
- 替换项目当前简历后，旧 Session 继续读取旧 Snapshot，新 Session 使用新版本。
- `use_resume_context=false` 不创建 Snapshot；`true` 但无 READY 版本时完整回滚。
- 已创建 Session 的 Snapshot 不能更新或更换。
- 简历独有技能不能成为 Planner 目标。
- 相同正式上下文在有无简历时选择相同能力、Indicator 和 Evidence Requirement。
- QuestionTool 可以改变问题表达，但不能改变正式评价目标和预期证据。
- EvidenceObservation 的所有来源片段均来自回答，不来自简历。
- 简历冲突只产生 `UNCERTAIN` 或中性追问，不自动产生负面证据。
- 状态、Evidence Package 和评分模块不依赖 Resume Context。
- 相同 Evidence Package 在有无简历时评分完全一致。
- 报告背景区与正式证据引用严格分离。
- 覆盖项目归属、文件名路径注入、HTML 注入和 Prompt 注入场景。

### 12.2 前端测试

- 无简历时旧创建流程与测评流程不变。
- 覆盖上传、解析中、失败、替换、取消使用和选择是否绑定。
- “仅用于个性化、不参与评分”提示可被辅助技术读取。
- 创建测评选择项正确映射 `use_resume_context`。
- 已创建 Session 不显示更换快照操作。
- 待确认背景与正式 Evidence 使用不同语义标签，不能只靠颜色区分。
- 报告明确区分简历背景和面试验证证据。
- 覆盖窄屏、键盘、焦点和状态播报。

### 12.3 核心不变量

```text
Formal target(with resume) == Formal target(without resume)
Score(with resume)         == Score(without resume)
Resume text                != EvidenceObservation source
Old Session snapshot       != Replaced current resume
```

## 13. 完成定义

- 可选简历的上传、版本替换、Session 快照和无简历降级流程可用。
- 现有 API 保持兼容，旧客户端缺省不使用简历。
- 正式目标、证据、状态、Evidence Package 和评分边界由自动化测试证明未受简历影响。
- 报告和 UI 明确区分背景信息与面试验证证据。
- 上传安全、隐私最小化、项目归属和 Prompt 注入约束有测试覆盖。
- 后端相关 pytest、前端 Vitest、必要 Playwright、构建和 `git diff --check` 实际通过。

