# 阶段二：结构化自适应测评与动态追问设计

## 1. 目标与范围

阶段二建立在阶段一已经确认并冻结的岗位胜任力模型之上，为用户提供完整的文字测评闭环：系统按能力项生成主问题，用户提交回答，AI 提取回答证据并生成必要的追问，程序控制测评顺序、轮次和完成条件，最终输出供阶段三消费的结构化测评证据包。

本阶段采用“结构化状态机 + AI 内容生成”架构。MVP 只支持文字输入和文字输出，默认覆盖模型中的全部核心能力项。阶段二不计算正式能力分数、岗位匹配度、雷达图或人才画像。

## 2. 设计原则与边界

- 阶段二只读取阶段一的已确认模型版本，不修改能力项、权重或 JD 证据。
- 程序负责状态、顺序、轮次、权限、Schema 校验和幂等；AI 负责问题生成、回答理解、证据提取和自然语言追问。
- AI 不得创建岗位模型之外的新能力，不得修改能力权重，也不能绕过程序结束或推进会话。
- 每个能力项包含 1 道主问题，最多 2 次追问。
- 一道主问题可以是综合题，覆盖多个相关能力项；综合题不把能力项合并为一个评价对象。
- 每个回答都保留原文、对话轮次和可追溯证据；阶段三只依赖版本化证据包。
- 测评结果是实验系统内部的辅助性结果，不构成正式招聘决策、心理测量或职业资格结论。

## 3. 状态机

### 3.1 测评会话状态

```text
READY -> IN_PROGRESS -> PAUSED -> IN_PROGRESS -> COMPLETED
                         |
                         -> FAILED
IN_PROGRESS -> PARTIALLY_FINISHED（用户主动结束）
```

- `READY`：会话已创建，尚未生成第一道题。
- `IN_PROGRESS`：允许生成问题和提交回答。
- `PAUSED`：保存进度但不允许提交回答。
- `COMPLETED`：全部核心能力项已处理，生成 `FULL` 证据包。
- `PARTIALLY_FINISHED`：用户主动结束，未完成项保留为 `INCOMPLETE`，生成 `PARTIAL` 证据包。
- `FAILED`：不可恢复的会话级失败；可通过创建新会话重测。

### 3.2 能力项状态

```text
PENDING -> ASKING -> FOLLOW_UP -> SUFFICIENT
                         |
                         -> EXHAUSTED
```

- `PENDING`：尚未开始。
- `ASKING`：主问题已生成，等待回答。
- `FOLLOW_UP`：正在等待追问后的回答。
- `SUFFICIENT`：已达到最低证据要求。
- `EXHAUSTED`：达到两次追问上限仍证据不足。

### 3.3 推进规则

用户提交回答后，后端保存回答并调用 AI 分析：

1. `SUFFICIENT`：当前能力项标记为 `SUFFICIENT`，选择下一个待测能力项。
2. 非 `SUFFICIENT` 且追问次数小于 2：追问次数加一，生成追问并保持当前能力项。
3. 非 `SUFFICIENT` 且已达到 2 次追问：标记为 `EXHAUSTED`，记录证据不足并进入下一个能力项。

程序规则优先于 AI 返回的推进建议。每次推进与回答、证据和事件写入同一事务；AI 调用失败时不推进能力项。

### 3.4 综合题与多能力证据

为避免用户被逐项重复询问，问题生成器可以将相关能力项组合为一道综合题，建议一次覆盖不超过 3 项能力。系统必须在问题卡片上明确显示“综合题 · 覆盖 N 项能力”和能力标签，并在服务端保存该题的 `covered_competency_ids`。

用户的一份回答先作为一个完整 `ANSWER` 轮次保存，再由 AI 返回按能力项拆分的证据观察。每条观察只归属于一个 `CompetencyAssessment`，因此同一回答可以产生多条不同能力的证据，但不能因为回答同时覆盖多个能力就自动完成所有能力项。每个能力项独立判断：

```text
综合题回答
  -> 系统设计：证据充分 -> SUFFICIENT
  -> 问题分析：证据不足 -> FOLLOW_UP（只追问问题分析）
  -> 沟通表达：证据充分 -> SUFFICIENT
```

定向追问只针对仍为 `INSUFFICIENT` 或 `UNCERTAIN` 的能力项，并将追问次数计入目标能力项，而不是计入整道综合题。右侧工作台显示每个能力项的独立状态，例如“证据充分”“本题观察”“追问中”；总体进度只统计已进入终态 `SUFFICIENT` 或 `EXHAUSTED` 的能力项。这样用户能够理解系统为什么不重复追问已充分的能力，同时阶段三仍能得到逐能力项的证据链。

单能力项问题使用同一套页面骨架，但隐藏综合题标签和证据分配面板：问题卡片只显示一个能力标签，右侧只高亮当前能力项，证据摘要直接归属于该能力项，定向追问明确写出“补充〈能力项〉证据”。其他能力项保持“未开始”或“已完成”，不因当前回答被动改变状态。单项题与综合题的差异只体现在覆盖能力数量和信息层级，不拆成两套页面。

## 4. 核心数据结构

```text
AssessmentSession
- id
- project_id
- model_version_id
- status
- completion: FULL | PARTIAL | NONE
- current_competency_id
- started_at / paused_at / completed_at

CompetencyAssessment
- id
- session_id
- competency_id
- status
- main_question
- follow_up_count
- evidence_sufficiency
- started_at / completed_at

AssessmentTurn
- id
- competency_assessment_id
- turn_index
- role: SYSTEM | USER
- turn_type: MAIN_QUESTION | ANSWER | FOLLOW_UP
- covered_competency_ids（系统问题轮次保存，回答轮次继承）
- content
- idempotency_key（用户回答可选）
- created_at

EvidenceObservation
- id
- competency_assessment_id
- turn_id
- evidence_type: POSITIVE | NEGATIVE | MISSING | UNCERTAIN
- summary
- source_excerpt
- confidence
- created_at

AssessmentEvent
- id
- session_id
- action
- payload
- created_at
```

## 5. AI 合约

每次 AI 调用只接收当前能力项、该能力项关联的 JD 证据、当前能力项已有对话和必要的测评规则。AI 返回必须符合以下结构：

```json
{
  "answer_summary": "用户回答的简要归纳",
  "evidence": [
    {
      "type": "POSITIVE | NEGATIVE | MISSING | UNCERTAIN",
      "summary": "证据说明",
      "source_excerpt": "回答中的原文片段",
      "confidence": 0.82
    }
  ],
  "evidence_sufficiency": "SUFFICIENT | INSUFFICIENT | UNCERTAIN",
  "needs_follow_up": true,
  "follow_up_reason": "需要补充的证据",
  "follow_up_question": "下一条追问"
}
```

程序校验：

- `confidence` 必须在 `0..1`；
- `source_excerpt` 必须能在用户回答原文中定位，否则降级为 `UNCERTAIN`；
- 证据类型和充分性必须属于枚举值；
- 追问只能关联当前能力项；
- AI 返回不得包含新能力项、权重或模型版本修改；
- 结构错误、空结果或越界结果都不得推进状态。

## 6. 端到端数据流

```text
读取已确认模型版本
  -> 创建 AssessmentSession
  -> 选择下一个待测能力项
  -> AI 生成主问题
  -> 用户提交回答
  -> 保存 USER turn
  -> AI 分析回答并提取证据
  -> Schema 校验并保存 EvidenceObservation
  -> 程序按规则推进能力项
  -> 返回下一条系统消息和进度
  -> 所有能力项处理完毕
  -> 生成版本化证据包
```

刷新页面或重新进入任务时，前端从服务端读取会话状态、最近对话和进度，不依赖浏览器本地状态。

## 7. API 契约

```text
POST /api/projects/{project_id}/assessments
GET  /api/assessments/{session_id}
POST /api/assessments/{session_id}/start
POST /api/assessments/{session_id}/turns
POST /api/assessments/{session_id}/pause
POST /api/assessments/{session_id}/resume
POST /api/assessments/{session_id}/finish
POST /api/assessments/{session_id}/retry
GET  /api/assessments/{session_id}/evidence-package
GET  /api/assessments/{session_id}/events
```

提交回答请求：

```json
{
  "content": "用户回答内容",
  "idempotency_key": "客户端生成的唯一键"
}
```

提交回答响应至少包含：

```json
{
  "session_status": "IN_PROGRESS",
  "current_competency": {},
  "next_message": {},
  "progress": {"completed": 3, "total": 8},
  "retryable": false
}
```

阶段一输入契约：已确认 `model_version_id` 及其能力项、权重、描述和 JD 证据引用。阶段二输出契约：

```json
{
  "session_id": "...",
  "model_version_id": "...",
  "completion": "FULL | PARTIAL",
  "competencies": [
    {
      "competency_id": "...",
      "status": "SUFFICIENT | EXHAUSTED | INCOMPLETE",
      "observations": [
        {
          "type": "POSITIVE | NEGATIVE | MISSING | UNCERTAIN",
          "summary": "...",
          "source_excerpt": "...",
          "turn_id": "...",
          "confidence": 0.82
        }
      ],
      "turn_ids": ["..."]
    }
  ]
}
```

## 8. 用户界面

沿用阶段一三栏 AppShell：

- 左侧保留历史任务和当前项目；
- 中间为测评对话区，显示能力项、问题、回答、追问、处理中和错误状态；
- 右侧为测评工作台，显示 `已完成 / 总能力项`、每项状态、暂停、继续和结束操作。

提交回答期间禁止重复发送。用户主动结束前明确提示未完成能力项数量；确认后生成 `PARTIAL` 证据包。完成后提供证据包查看入口，不在阶段二展示正式分数。

### 8.1 阶段二工作台信息结构

右侧工作台按以下顺序组织，保证用户先理解“现在在哪”，再决定“下一步做什么”：

1. **会话状态栏**：岗位名称、绑定模型版本、会话状态（准备中/进行中/已暂停/已完成）和暂停/继续/结束操作。
2. **进度区**：`已完成能力项 / 总能力项`、线性进度条和当前问题覆盖的能力项；综合题覆盖但尚未进入终态的能力项不计入已完成数量，进度必须同时提供文字，不得只依靠颜色或图形。
3. **能力项列表**：每项显示名称、状态徽标、主问题/追问数量和证据充分度。当前项使用高亮边框与“当前”文字标识，不能仅使用颜色区分。
4. **证据摘要区**：当前能力项已提取的正向、负向、不确定和缺失证据数量；点击后打开统一 `EvidenceDrawer`，查看来源回答原文和对应轮次。
5. **操作区**：暂停、继续、结束测评和查看证据包。高影响的“结束测评”必须使用确认对话框，并明确未完成项数量及 `PARTIAL` 结果含义。

### 8.2 对话区状态与组件

阶段二专属组件沿用全局组件契约，并补充以下状态：

- `AssessmentIntroCard`：说明测评范围、每项最多两次追问、预计流程和数据用途；只在会话尚未开始时显示。
- `QuestionBubble`：显示当前主问题或追问，标记关联能力项；综合题使用“综合题 · 覆盖 N 项能力”标签和多个能力标签；系统消息与用户回答使用不同语义样式。
- `AnswerComposer`：多行文本输入、提交按钮、字符数提示和提交中状态；提交期间禁用重复发送，但保留已输入内容直到服务端确认。
- `ThinkingIndicator`：显示“正在分析回答/正在生成追问”等具体步骤，不使用无意义的无限旋转。
- `EvidenceInlineCard`：在回答分析后以折叠卡片显示证据数量和充分度；综合题展开后按能力项分组展示证据分配、充分度和定向追问原因，再进入证据抽屉。
- `AssessmentCompletionCard`：显示完成类型（完整/部分）、已完成项与未完成项，并提供查看证据包入口。
- `RetryNotice`：AI 超时或返回结构错误时，靠近当前回答显示原因、重试按钮和“保留回答继续”说明。

### 8.3 视觉与排版约束

阶段二继承[全局交互基线设计](../../design/00-全局交互基线设计.md)的温和专业、低饱和青绿色视觉方向，不采用与全局基线冲突的紫色渐变或装饰性 AI 光效。建议实现时使用语义化设计令牌：

```text
--surface-canvas: 暖白
--surface-panel: 近白
--text-primary: 深青灰
--text-secondary: 中性灰
--accent-primary: 低饱和青绿
--state-success: 深绿色
--state-warning: 琥珀色
--state-danger: 深红色
--border-subtle: 低对比边框
--focus-ring: 高对比青绿色
```

正文基准字号不小于 `16px`，行高建议 `1.5`；题目和回答使用较宽的阅读列，单行长度避免过长。能力项状态、证据类型和错误状态必须同时使用文字与图标/结构表达。图标采用统一 SVG 图标库，不使用 emoji 作为功能图标。

### 8.4 响应式断点与面板行为

- `>= 1440px`：折叠导航 + 对话区 + 右侧常驻工作台；工作台可收窄但不可压缩到无法阅读。
- `1024px–1439px`：保留三栏，但默认收窄左导航；工作台允许在常驻和滑出之间切换。
- `768px–1023px`：优先显示对话区，工作台改为右侧抽屉；底部提供“对话/工作台”切换入口。
- `< 768px`：主对话区单栏显示，工作台接近全屏从右侧滑入；打开时锁定背景滚动，关闭后恢复触发按钮焦点、对话滚动位置和未发送草稿。

核心操作不得依赖横向滚动。触控目标最小为 `44×44px`，抽屉和确认框支持 Escape 关闭、焦点陷阱和关闭后的焦点回归。

### 8.5 动效与反馈

动效只表达状态连续性：新问题进入、回答提交、工作台抽屉打开和状态徽标变化。常规过渡控制在 `150–250ms`，避免对话内容大幅位移；`prefers-reduced-motion: reduce` 下直接呈现最终状态。长任务必须显示具体阶段（提交中、分析中、生成追问中），错误提示靠近触发位置并提供可恢复动作。

### 8.6 阶段二 UI 验收

- 用户不看接口即可理解当前能力项、已完成数量、追问次数和下一步动作。
- 综合题能够明确显示覆盖的能力项；同一回答的证据分配可按能力项查看，且定向追问只显示证据不足的能力项。
- 单项题不显示多能力分配面板，用户能直接看出当前能力、证据摘要和追问次数；单项题与综合题切换时页面骨架和输入位置不改变。
- 主问题、回答、追问和证据卡在对话区按时间顺序呈现，刷新后顺序和状态不变。
- 桌面端工作台常驻，窄屏工作台可从右侧打开且不产生核心内容横向溢出。
- 提交中、AI 分析中、超时、重试、暂停、完成和部分完成均有明确可见状态。
- 键盘可以完成开始、回答提交、暂停、恢复、打开证据抽屉和结束确认；所有交互元素有可见焦点。
- 在 `375px`、`768px`、`1024px` 和 `1440px` 宽度下，题目、回答和操作按钮均可读且不被固定元素遮挡。

## 9. 失败处理与恢复

- AI 超时或网络错误：保留当前能力项和用户回答，标记可重试。
- AI Schema 校验失败：记录 `AI_INVALID_RESPONSE`，不推进状态，允许重试。
- 连续失败达到实现阶段定义的阈值：当前能力项标记 `EXHAUSTED`，保留原回答并继续测评。
- 重复幂等键：返回既有处理结果，不重复创建回答、证据或追问。
- 浏览器刷新：从服务端状态恢复。
- 已完成或已部分结束会话：拒绝追加回答；重测创建新的 `session_id`。

## 10. 事件类型

```text
ASSESSMENT_CREATED
ASSESSMENT_STARTED
MAIN_QUESTION_GENERATED
ANSWER_SUBMITTED
ANSWER_ANALYZED
EVIDENCE_RECORDED
FOLLOW_UP_GENERATED
COMPETENCY_SUFFICIENT
COMPETENCY_EXHAUSTED
ASSESSMENT_PAUSED
ASSESSMENT_RESUMED
ASSESSMENT_COMPLETED
ASSESSMENT_PARTIALLY_FINISHED
AI_RETRY_REQUESTED
AI_INVALID_RESPONSE
```

## 11. 测试与验收

### 11.1 自动化测试

- 状态机：充分证据、追问、追问上限、暂停恢复、主动结束、完成后拒绝提交。
- AI 合约：合法响应、枚举越界、置信度越界、证据片段无法定位、越权创建能力项。
- API 集成：完整测评、刷新恢复、幂等提交、AI 超时重试、`PARTIAL` 证据包。
- 前端：问题/回答顺序、提交中禁用、错误重试、能力项进度和完成入口。

### 11.2 演示验收

必须跑通：

```text
选择已确认模型 -> 创建会话 -> 生成主问题 -> 提交回答
-> 必要时最多追问 2 次 -> 切换能力项 -> 暂停/恢复
-> 完成全部能力项 -> 生成 FULL 证据包
```

同时演示：AI 超时可重试、非法结构不丢回答、用户主动结束生成 `PARTIAL`、重复提交不产生重复记录。

## 12. 明确不做

- 语音输入、语音识别和实时音视频；
- 在线代码执行或沙箱；
- 多人面试与协同评分；
- 阶段三的正式评分、雷达图、匹配度和人才画像；
- 自动招聘决策或录用建议；
- 主动抓取招聘网站数据。
