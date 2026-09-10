# 岗位能力评估 Agent 渐进式架构升级设计

> 文档状态：已确认设计
> 日期：2026-09-10
> 关联规格：`2026-09-09-stage2-adaptive-assessment-design.md`、`2026-09-09-stage2-frontend-ui-design.md`、`2026-09-09-stage3-capability-evaluation-profile-design.md`

## 1. 目标

在不改变现有测评 API、数据库结构和确定性业务规则的前提下，为阶段二测评流程增加显式的 Agent、Planner、Memory 和 Tools 边界，使一次回答处理通过 `InterviewAgent` 编排，同时保留现有状态机、证据追溯、幂等、暂停恢复、证据包和阶段三报告能力。

本次是兼容门面式迁移，不追求一次性把 `assessment_service.py` 搬空，也不引入多 Agent、自主状态推进或新的持久化表。

## 2. 不可破坏的边界

- 现有测评路由、请求字段和响应字段继续可用；新增响应字段必须是可选、向后兼容的。
- 不修改已有数据库表，不新增 `AgentAction`、`MemorySnapshot` 或 `QuestionMetadata` 表。
- `assessment_state.py` 继续唯一负责追问上限、能力终态、当前能力推进、会话完成条件和部分结束规则。
- Planner 不得绕过状态机，不得修改岗位模型、能力权重、用户回答、证据原文或历史事件。
- 阶段二只生成问题、分析回答和整理证据；不得调用评分或报告生成能力。
- `ScoringTool` 和 `ReportTool` 只作为阶段三服务的显式适配器存在，由阶段三调用方使用。
- AI 返回仍需通过现有 Pydantic Schema、能力归属、置信度和原文片段校验。
- 没有 API Key 时继续支持确定性演示流程。
- 用户当前在 `analysis`、`parsing` 和配置相关文件中的未提交修改不属于本任务，不得覆盖或整理。

## 3. 方案选择

采用兼容门面式迁移：新 Agent 层复用已有状态机和服务能力，`assessment_service` 保留 API 事务入口并逐步委托 Agent。

未采用影子运行方案，因为它不能让真实提交回答链路经过 Agent；未采用一次性完全迁移方案，因为它会同时改变事务、幂等、错误恢复和事件记录，回归风险过高。

## 4. 目标目录

```text
backend/app/agent/
├── __init__.py
├── schemas.py
├── memory.py
├── planner.py
├── interview_agent.py
└── tools/
    ├── __init__.py
    ├── question.py
    ├── evidence.py
    ├── scoring.py
    └── report.py
```

每个文件保持单一职责：Schema 定义稳定接口，Memory 只读聚合上下文，Planner 只产生受约束决策，Tools 只适配现有能力，InterviewAgent 负责编排一次回答处理。

## 5. Agent Schema

`agent/schemas.py` 定义以下内部模型：

```python
class AgentAction(str, Enum):
    FOLLOW_UP = "FOLLOW_UP"
    NEXT_COMPETENCY = "NEXT_COMPETENCY"
    FINISH = "FINISH"

class PlannerContext(BaseModel):
    session_id: str
    session_status: str
    current_competency_id: str | None
    competencies: list[CompetencyMemoryItem]
    conversation: list[ConversationMemoryItem]
    evidence: list[EvidenceMemoryItem]
    remaining_competency_ids: list[str]

class PlannerDecision(BaseModel):
    action: AgentAction
    target_competency_id: str | None
    reason: str
    question_goal: str | None = None

class AgentStatus(BaseModel):
    phase: str
    confirmed_competency_ids: list[str]
    active_competency_id: str | None
    pending_evidence: list[str]
    reason: str | None = None

class AgentTurnResult(BaseModel):
    decision: PlannerDecision
    current_question: dict | None
    agent_status: AgentStatus
    retryable: bool = False
    error: str | None = None
```

内部枚举使用 `FOLLOW_UP | NEXT_COMPETENCY | FINISH`。API 若需要展示动作，通过新增可选 `agent_status` 暴露摘要，不替换现有 `current_question`、`status`、`progress` 等字段。

## 6. Memory 设计

`AssessmentMemory` 是现有持久化数据的查询型投影，不持有第二份事实源。

主要接口：

```python
class AssessmentMemory:
    def get_context(self, session: AssessmentSession) -> PlannerContext: ...
    def get_conversation(self, session_id: str) -> list[ConversationMemoryItem]: ...
    def get_evidence(self, session_id: str) -> list[EvidenceMemoryItem]: ...
    def get_competencies(self, session: AssessmentSession) -> list[CompetencyMemoryItem]: ...
```

“更新 Memory”不单独写入存储。回答、证据和能力状态仍由现有事务写入对应表；事务 flush 后再次读取 Memory 即得到最新上下文。为兼容任务说明，可以提供 `update_evidence()` 和 `update_competency_state()` 方法，但它们只委托现有持久化/状态服务，不能绕过校验或创建重复数据。

Memory 输入遵循最小上下文原则：Planner 只获得决策所需的能力状态、证据摘要、问题与回答，不获得无关项目或其他会话数据。

## 7. Tools 设计

### 7.1 QuestionTool

适配 `assessment_ai.generate_main_question`，接收已确认岗位快照、目标能力、JD 证据、历史问题和已有证据。输出沿用 `GeneratedQuestion`，并向后兼容增加：

- `evaluation_target: str | None`
- `expected_evidence: list[str]`

缺少 API Key 或供应商失败时继续使用现有确定性问题生成策略。

### 7.2 EvidenceTool

适配 `assessment_ai.analyze_answer` 和 `validate_analysis`。它只返回校验后的分析结果，不直接推进状态。分析输出继续包含逐能力证据、充分性、追问理由和追问问题；`missing_information` 通过现有 `follow_up_reason` 表达，避免同时维护两个含义重叠的事实字段。

### 7.3 ScoringTool

适配 `services/scoring.py` 的阶段三确定性评分能力。它不被 `InterviewAgent` 或任何阶段二流程导入或调用。

### 7.4 ReportTool

适配 `services/report_service.py` 的版本化报告生成能力。它不被 `InterviewAgent` 或任何阶段二流程导入或调用。

Tools 不拥有事务，不直接提交数据库，也不改变状态机。

## 8. Planner 设计

第一版 Planner 采用确定性规则，预留受约束的 LLM 辅助接口，但不要求启用 LLM Planner。

Planner 输入为 `PlannerContext` 和状态机已经产生的 transition 结果。Planner 输出必须满足：

- 状态机要求追问时，只能输出 `FOLLOW_UP`，目标必须是该 transition 对应能力。
- 状态机已推进且会话仍在进行时，只能输出 `NEXT_COMPETENCY`，目标必须等于服务端 `current_competency_id`。
- 状态机已完成时，只能输出 `FINISH`，目标为空。
- Planner 返回越权目标、未知动作或与会话状态冲突时，拒绝结果并使用确定性 Planner 决策。

Planner 的 `reason` 和 `question_goal` 用于可解释展示和问题生成上下文，不作为状态推进依据。

## 9. InterviewAgent 编排

`InterviewAgent` 通过构造函数注入数据库会话、Memory、Planner 和 Tools，方便测试替换。

```python
class InterviewAgent:
    def process_turn(
        self,
        session: AssessmentSession,
        answer: AssessmentTurn,
        *,
        retry: bool = False,
    ) -> AgentTurnResult: ...
```

编排顺序：

1. 校验会话、回答和问题覆盖能力属于同一会话。
2. 通过 Memory 读取最小上下文。
3. EvidenceTool 对回答按覆盖能力逐项分析。
4. 保存经过校验的 EvidenceObservation 和对应事件。
5. 调用现有 `apply_analysis` 更新能力与会话状态。
6. Memory 重新读取更新后的上下文。
7. Planner 根据状态机 transition 生成受约束决策。
8. `FOLLOW_UP` 或 `NEXT_COMPETENCY` 时调用 QuestionTool 创建下一问题；`FINISH` 时记录完成事件。
9. 返回 `AgentTurnResult`，由服务层提交事务并序列化现有响应。

AI 可重试错误不推进状态，不重复保存证据，保留用户回答，并返回 `retryable=True`。非法 AI 结构继续记录 `AI_INVALID_RESPONSE`，行为与现有接口一致。

## 10. Service 集成与事务

`assessment_service.py` 继续负责：

- 路由可调用的兼容函数；
- 创建会话、开始、暂停、恢复和主动结束；
- 幂等键检查与 USER turn 创建；
- 顶层事务 commit/rollback；
- 会话响应序列化。

`submit_turn()` 创建并 flush 回答后调用 `InterviewAgent.process_turn()`。`retry_turn()` 找到原回答后调用同一方法并传入 `retry=True`。原 `_analyze_targets()` 和 `_process_answer()` 的业务逐步迁入 Agent，待测试覆盖后从 Service 删除，避免维护两套执行路径。

单次回答、证据、状态、问题和事件仍在一个数据库事务中完成。任何非可重试异常由 Service 回滚；可重试 AI 错误仅提交回答和重试事件，不提交能力推进。

## 11. Prompt 增强

保留 `assessment_prompts.py`，不在本轮拆分模板目录。问题生成上下文增加：

- 岗位与已确认模型版本；
- 目标能力要求；
- 当前能力状态；
- 已有证据摘要；
- 缺失信息；
- 历史问题，避免重复。

问题生成结构化输出兼容现有字段：

```json
{
  "content": "问题文本",
  "covered_competency_ids": ["..."],
  "turn_type": "MAIN_QUESTION",
  "evaluation_target": "本题验证目标",
  "expected_evidence": ["期望事实或结果"]
}
```

新增字段设置默认值，旧供应商响应仍可通过校验。回答分析继续沿用现有结构，`follow_up_reason` 作为缺失信息的规范字段。

## 12. API 和前端适配

现有快照响应新增可选字段：

```json
{
  "agent_status": {
    "phase": "EVALUATING | FOLLOWING_UP | MOVING_NEXT | COMPLETED | RETRY_REQUIRED",
    "confirmed_competency_ids": ["c-1"],
    "active_competency_id": "c-2",
    "pending_evidence": ["缺少可验证的项目结果"],
    "reason": "当前能力仍缺少结果证据"
  }
}
```

前端在 `AssessmentWorkbench` 内增加 Agent 状态区，使用服务端给出的能力 ID 映射现有能力名称，展示：

- 已确认的能力；
- 当前验证能力；
- 等待补充的证据；
- 当前决策原因。

状态同时使用文字、结构和现有语义样式表达，不增加评分条、百分比或阶段三结论。Agent 状态缺失时组件不渲染该区域，保证旧后端兼容。窄屏继续随现有工作台进入抽屉，不新建页面或固定浮层。

## 13. 错误与恢复

- AI 超时、限流或供应商故障：保留回答，返回 `RETRY_REQUIRED`，不推进状态。
- AI Schema 或证据归属非法：记录 `AI_INVALID_RESPONSE`，不生成问题或更新能力状态。
- Planner 非法决策：记录内部诊断事件并回退到确定性决策；不得让用户回答丢失。
- 问题生成失败：使用现有确定性问题模板，不阻塞核心演示流程。
- 重复幂等键：返回已有会话快照，不重复运行 Agent。
- 重试同一回答：不得重复创建证据；实现需要在写入前识别该回答是否已有完成的分析记录。
- 暂停、完成或部分结束的会话拒绝新回答，沿用现有错误码。

## 14. 测试策略

### Agent 单元测试

- Memory 只读取指定会话，并正确聚合对话、证据与能力状态。
- Planner 对追问、切换能力和完成分别返回唯一合法动作。
- Planner 无法修改状态机结果或选择模型外能力。
- QuestionTool 和 EvidenceTool 正确转发结构化上下文并保留确定性降级。
- ScoringTool、ReportTool 适配既有服务，但不出现在阶段二 Agent 依赖图中。

### Service 与 API 集成测试

- 提交回答真实经过 `InterviewAgent`。
- 充分证据推进下一能力；不足证据定向追问；达到上限进入 `EXHAUSTED`。
- 综合题仍按能力独立分析。
- 重复幂等提交和失败重试不产生重复回答、证据或问题。
- 暂停恢复、主动结束、完整完成和证据包行为不变。
- 新增 `agent_status` 不删除或重命名任何旧字段。

### 前端测试

- 有 Agent 状态时显示已确认、正在验证和待补充证据。
- 没有 Agent 状态时保持旧布局可用。
- 不显示评分、岗位匹配度或人才画像结论。
- 状态不只依靠颜色表达，并具有可读标题和文本。

### 回归验证

执行最窄相关 pytest/Vitest 测试后，运行后端完整测试、前端测试、生产构建、阶段二 Playwright 流程和 `git diff --check`。

## 15. 本轮明确不做

- 新增 Agent 持久化表或数据库迁移；
- LLM 自主控制状态机；
- 动态改变最多两次追问的已确认规则；
- 情绪识别、心理测量或候选人性格推断；
- 多 Agent 协作、语音面试或代码执行；
- 在阶段二计算或展示正式评分、匹配度、雷达图和人才画像；
- 拆分 `assessment_prompts.py` 为模板目录；
- 修改阶段一解析流程或用户当前未提交文件。

## 16. 验收条件

- 回答提交链路为 `submit_turn -> InterviewAgent -> EvidenceTool -> assessment_state -> Planner -> QuestionTool/FINISH`。
- 代码中存在可独立测试的 Agent、Planner、Memory 和四个 Tool 适配器。
- 所有现有测评路由和字段保持兼容，新增 Agent 状态为可选字段。
- 数据库结构不变，状态事实仍来自后端快照和既有表。
- 阶段二边界、证据追溯、幂等、失败恢复和最多两次追问不变量保持成立。
- 创建、开始、回答、暂停恢复、完整/部分证据包和报告生成回归测试均通过。
- 前端可解释展示 Agent 当前状态，但不展示阶段三正式结论。
