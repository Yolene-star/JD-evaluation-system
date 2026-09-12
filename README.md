# JD Evaluation System

AI 驱动的岗位胜任力测评与人才画像系统，面向学生自测、模拟面试和教学实验。系统把 JD 转换为版本化胜任力模型，通过自适应文字面试收集可追溯证据，再生成辅助性能力评价与人才画像。

> 所有评分和报告都是辅助性结果，不构成正式招聘决策、心理测量或职业资格结论。

## 程序定位与语言交互

这是一个支持自然语言交互的 AI 应用程序。用户可以通过对话输入岗位需求、补充或修订材料、询问模型依据，也可以在测评过程中直接用自然语言回答问题。系统中的 Agent 负责理解用户意图、生成问题、识别回答中的能力证据并解释报告；确定性程序负责状态流转、版本冻结、证据引用、权重聚合和评分计算。

语言交互贯穿三个阶段：阶段一用于核对 JD、解释能力项并辅助完成岗位模型；阶段二用于开展多轮自适应文字测评和追问；阶段三用于根据已生成的报告回答评分依据、证据来源和改进建议。用户也可以使用文字、文件、链接或浏览器提取方式补充 JD。自然语言交互不会绕过权限、状态和版本校验，Agent 也不能直接修改正式评分、历史报告或已冻结模型。

## 三阶段闭环

```text
JD / 简历（可选） → 阶段一岗位模型 → 阶段二自适应面试 → 阶段三评分、报告与咨询
```

### 阶段一：JD 分析与岗位模型

- 支持文字、文件、链接和浏览器提取 JD；
- 解析能力项、描述、权重、指标、证据要求和 JD 原文证据；
- 支持能力聚合、权重归一化、冲突处理和人工增删改；
- 通过 `ModelVersion` / `ModelSnapshot` 保存不可变确认版本；
- 已确认模型不能直接修改，调整必须创建新版本；
- Stage 1 Agent 可识别意图，但增删改必须经过受控操作和状态校验。

### 阶段二：自适应文字测评

- 只能基于阶段一 `CONFIRMED` 模型出题；
- `InterviewAgent` 协调 Memory、Planner、QuestionTool 和 EvidenceTool；
- LLM 判断回答质量、命中指标和证据缺口，确定性 fallback 支持无 Key 演示；
- 支持 `OPEN_EXPLORATION`、`DETAIL_PROBE`、`TECHNICAL_DEEPEN`、`RESULT_VERIFY`、`SCENARIO_TEST`；
- 支持追问上限、暂停、恢复、重试、幂等提交和自动进入下一题；
- 只有用户回答片段才能成为 `EvidenceObservation`；
- 简历是可选 Candidate Context，只用于个性化，不直接进入证据、状态或评分；
- Session 冻结 Model Snapshot 和可选 Resume Snapshot，历史测评不受后续替换简历影响。

### 阶段三：能力评价与人才画像

- 只读取终态 `FULL` 或 `PARTIAL` Evidence Package；
- 程序负责评分、权重聚合、完成度和未评价能力处理；
- LLM 只生成受约束的自然语言解释、优势、短板和建议；
- 报告绑定 Session、Model Version、Evidence Package、Rubric 和评分规则版本；
- 指标、证据和能力名称显示为可读文本，内部 ID 仅用于审计；
- 咨询 Agent 只解释报告，不修改分数、模型、证据或历史报告；
- 报告区分“简历背景信息”和“面试验证证据”。

## Agent 架构

```text
backend/app/agent/
├── interview_agent.py   # 一次回答的完整处理流程
├── planner.py           # 正式评估目标和问题策略
├── memory.py            # 对话、证据、能力状态和简历上下文
├── schemas.py           # Agent 决策与状态契约
└── tools/               # 问题、证据、评分、报告工具抽象
```

Planner 不能修改状态或直接写数据库；状态转移必须经过 `assessment_state.py`。阶段二不得调用阶段三评分和报告服务。

## 主要 API

### 项目、JD 与模型

- `POST /api/projects`、`GET /api/projects`、`DELETE /api/projects/{project_id}`
- `POST /api/projects/{project_id}/jds/text|file|link|browser`
- `POST /api/projects/{project_id}/analysis/run`
- `GET /api/projects/{project_id}/analysis`
- `POST /api/projects/{project_id}/aggregate`
- `POST /api/models/{model_id}/confirm`

### 阶段二测评

- `POST /api/projects/{project_id}/assessments`
- `POST /api/assessments/{session_id}/start`
- `POST /api/assessments/{session_id}/turns`
- `POST /api/assessments/{session_id}/pause|resume|finish|retry`
- `GET /api/assessments/{session_id}`、`/events`、`/evidence-package`

提交回答必须携带唯一 `idempotency_key`，重复提交不会重复创建回答、证据、问题或状态转移。

### 简历上下文

- `POST/GET/DELETE /api/projects/{project_id}/resume-context`

项目级简历可替换；已开始 Session 使用冻结快照，历史测评不会被后续替换影响。

### 阶段三报告与咨询

- `POST/GET /api/assessment-sessions/{session_id}/reports`
- `GET /api/reports/{report_id}`
- `POST /api/reports/{report_id}/narrative/retry`
- `GET /api/reports/{report_id}/scoring-policy`
- `GET/POST /api/reports/{report_id}/chat/messages`

## 技术栈与启动

- 后端：Python 3.11+、FastAPI、SQLAlchemy、Pydantic；
- 数据库：SQLite（本地/测试）、PostgreSQL（部署）、Alembic（迁移）；
- 前端：React、TypeScript、Vite；
- AI：OpenAI 兼容接口，默认适配 DeepSeek；
- 测试：pytest、Vitest、Playwright。

复制配置并启动：

```powershell
Copy-Item backend/.env.example backend/.env
.\start_project.ps1
```

按需配置 `DEEPSEEK_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`。无 API Key 时，确定性解析器和 fallback 仍可演示核心流程。

服务地址：

- 前端：`http://127.0.0.1:5192/`
- 后端：`http://127.0.0.1:8001/`
- 浏览器 JD 提取服务：`http://localhost:8787/`

## 数据库迁移

Alembic 配置位于 `backend/alembic.ini`：

```powershell
cd backend
python -m alembic upgrade head
python -m alembic check
```

迁移前审查 autogenerate 结果，不删除历史快照、证据包或报告。

## 质量测试样例集

仓库提供两层质量数据：

- `harness/fixtures/quality/samples.jsonl`：100 条脱敏混合回归样例；
- `harness/fixtures/quality/jd_reference_models.jsonl`：192 条独立 JD 与人工维护的参考岗位模型。

100 条混合样例分布如下：

| 样例类型 | 数量 | 覆盖内容 |
|---|---:|---|
| JD 解析 | 50 | 10 类岗位、标准/简洁/重复/低信息量/提示注入等表达 |
| 回答分析 | 35 | 充分回答、短回答、拒绝回答、空回答与提示注入 |
| 评分边界 | 5 | `INCOMPLETE`、满覆盖、半覆盖、负向和不确定证据 |
| 引用校验 | 5 | 原文、空白归一化、改写、空证据和标点差异 |
| 问题契约 | 5 | 1 至 3 项唯一能力、空范围、越界和重复 ID |

192 条 JD 参考集覆盖 24 个岗位族、4 个资历层级和多种行业、地点、表达风格，每条包含能力权重、别名、指标、证据要求和可回溯原文。

重新生成并运行回归：

```powershell
python harness/generate_quality_samples.py
python harness/generate_jd_reference_models.py
python -m pytest backend/tests/test_quality_samples.py -q
python -m pytest backend/tests/test_jd_reference_models.py backend/tests/test_jd_quality_metrics.py -q
```

无 API Key 时可运行确定性基线：

```powershell
python harness/quality_runner.py check
python harness/quality_runner.py run --model deterministic-fallback --sample-size 20
```

配置 Key 后可比较真实模型：

```powershell
python harness/quality_runner.py run --model deepseek-chat --sample-size 20
python harness/quality_runner.py run --model deepseek-reasoner --sample-size 20
```

2026-09-12 的实际对比见 `docs/quality/2026-09-12-model-comparison.md`。样例不包含真实个人数据；确定性回退只用于教学和回归，不代表真实大模型的专业评价质量。

## 本地验证

```powershell
python -m pytest backend/tests -q
npm --prefix frontend run test
npm --prefix frontend run test:e2e
npm --prefix frontend run build
git diff --check
```

## 目录索引

```text
backend/app/agent/       Agent、Planner、Memory、Tools
backend/app/services/    解析、状态机、证据、评分、报告和隐私逻辑
backend/app/routes/      FastAPI API 路由
backend/alembic/         数据库迁移配置
backend/tests/           后端契约、状态机和三阶段测试
prompts/                 版本化 Prompt、Schema 和清单
harness/fixtures/quality/ 100 条混合样例和 192 条 JD 参考模型
harness/quality_runner.py 离线和多模型质量评测 Runner
frontend/src/            React 应用与三阶段工作台
frontend/tests/           Vitest/Playwright 测试
docs/                    规格、实施计划和隐私说明
```

## 隐私与安全边界

- JD、简历、LLM 输出和用户回答均视为不可信输入；
- 日志不记录完整简历和完整回答，密钥不得进入仓库；
- 简历不能直接生成正式证据、能力状态或评分；
- 正式结论必须回溯到原始 JD 或用户面试回答；
- 缺少证据时显示“待补充”“不确定”或“未评价”，不得推测补全。

三阶段实施计划见：[2026-09-12-three-stage-project-plan.md](docs/superpowers/plans/2026-09-12-three-stage-project-plan.md)。
