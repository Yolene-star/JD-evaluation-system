# 开发验证 Harness 设计规格

> 状态：设计已确认，待实现计划
>
> 适用范围：本地 Windows 开发、GitHub Actions CI、三阶段核心业务的可重复验证
>
> 不包含：真实模型质量评测平台、生产监控、部署编排、恶意招聘网站数据抓取

## 1. 目标

本 Harness 为项目提供一套本地与 CI 共用的开发验证底座，解决以下问题：

- 没有 API Key 时仍可稳定演示和测试核心闭环；
- 后端、前端、数据库和浏览器测试使用同一套场景与配置；
- 测试验证真实 API、状态机、数据库和 UI 边界，不通过测试专用捷径绕过业务流程；
- AI 调用的不确定性被隔离为可重复的 Mock AI 场景；
- 失败时自动保留足够的日志、截图、trace 和临时数据库，便于定位；
- 本地 Windows 与 GitHub Actions 使用同一套 Python 编排逻辑。

Harness 不是业务服务，也不是第二套应用后端。它只负责准备环境、替换外部模型依赖、编排验证、收集结果和清理进程。

## 2. 非目标与约束

首版不做以下事情：

- 不连接真实招聘网站，不实现主动爬虫；
- 不把真实 LLM 调用作为合并门禁；
- 不把测试夹具写入正式业务数据库；
- 不为每个测试复制一套 API 或状态机；
- 不引入 Docker 作为本地运行前置条件；
- 不实现阶段四的完整 AI 质量评测平台；阶段四可复用本 Harness 的 fixture、报告和运行 ID 能力；
- 不因 Harness 建设提前实现阶段二或阶段三尚未具备的业务功能。

## 3. 采用方案

采用“Python Harness CLI 为核心，PowerShell 与 CI 为薄包装”的方案。

### 3.1 方案比较

| 方案 | 优点 | 问题 | 结论 |
|---|---|---|---|
| PowerShell 主导 | 当前 Windows 使用方便 | CI、跨平台和结构化报告维护成本高 | 不采用 |
| Python CLI + PowerShell/CI 包装 | 本地与 CI 复用逻辑，适合 Python 后端，可测试和扩展 | 需要维护少量进程管理代码 | 采用 |
| Docker Compose 主导 | 环境隔离强 | 当前项目尚无源码骨架，引入成本过高 | 暂不采用 |

### 3.2 目录布局

第一版建议创建：

```text
harness/
  cli.py
  config.toml
  fixtures/
    jd/
    ai/
    projects/
    scenarios/
  mock_ai/
  runners/
  reports/
scripts/
  harness.ps1
.github/
  workflows/
    ci.yml
```

`harness/reports/` 中的运行产物不得默认纳入版本控制；仓库只提交必要的目录说明或 `.gitkeep`。

## 4. 命令接口

Windows 本地统一从 PowerShell 入口调用：

```powershell
pwsh ./scripts/harness.ps1 doctor
pwsh ./scripts/harness.ps1 test --scope unit
pwsh ./scripts/harness.ps1 test --scope contract
pwsh ./scripts/harness.ps1 test --scope e2e
pwsh ./scripts/harness.ps1 verify
pwsh ./scripts/harness.ps1 demo
```

PowerShell 只负责转发退出码、传递参数和处理 Windows 中断；业务逻辑必须进入 Python CLI。CI 直接调用等价的 Python 命令，不依赖 PowerShell 专属实现。

### 4.1 `doctor`

检查并输出机器可读和人类可读结果：

- Python 版本是否满足项目要求；
- Node.js、npm 版本是否可用；
- Playwright 浏览器是否已安装；
- 后端和前端目录、测试目录、配置文件是否符合当前阶段；
- 临时目录是否可写；
- 端口是否可用；
- 必需环境变量是否存在；
- Mock AI 是否可加载。

尚未实现的目录不应被误报为 Harness 自身损坏；命令应区分“环境错误”和“项目阶段尚未实现”。

### 4.2 `test`

`--scope` 允许 `unit`、`contract`、`e2e` 和 `all`。支持以下通用参数：

- `--scenario <name>`：选择 Mock AI 场景；
- `--run-id <id>`：指定可复现运行标识；缺省时由 Harness 生成；
- `--keep-going`：某一层失败后继续执行后续层；
- `--keep-artifacts`：成功时也保留临时目录、日志和数据库；
- `--verbose`：输出子进程完整日志。

### 4.3 `verify`

默认顺序如下，前一步失败后停止；使用 `--keep-going` 可收集多个失败：

1. Harness 自检；
2. 后端 pytest；
3. API 契约测试；
4. 前端组件测试；
5. 前端生产构建；
6. Playwright 关键流程；
7. `git diff --check`；
8. 生成摘要报告。

当某个阶段目录或命令尚未实现时，Harness 应返回明确的 `NOT_IMPLEMENTED` 阶段状态，而不是伪造成功。MVP 的实际门禁由已实现阶段决定，并在报告中标记覆盖范围。

### 4.4 `demo`

`demo` 创建隔离数据库，启动后端和前端，使用 Mock AI 跑通当前已实现的最小垂直切片。目标流程为：

```text
JD 导入
→ JD 解析
→ 能力模型查看/确认
→ 测评开始
→ 回答与追问
→ 证据包交接
```

在阶段三尚未实现时，demo 不得伪造正式评分、岗位匹配度、雷达图或人才画像；应在证据包交接处结束并报告阶段边界。

## 5. 配置 Schema

配置使用 TOML，并允许环境变量覆盖敏感值和 CI 差异。建议字段如下：

```toml
[project]
python_command = "python"
node_command = "node"
npm_command = "npm"
backend_dir = "backend"
frontend_dir = "frontend"

[runtime]
backend_host = "127.0.0.1"
backend_port = 18080
frontend_host = "127.0.0.1"
frontend_port = 15173
health_timeout_seconds = 30
process_timeout_seconds = 180
keep_artifacts_on_failure = true

[ai]
provider = "mock"
scenario = "happy_path"
seed = "20260909"
max_retries = 1

[reports]
directory = "harness/reports"
redact_payloads = true
capture_playwright_trace = true
capture_screenshot_on_failure = true
```

实际端口和临时目录应在每次运行时解析为运行上下文，不得让并行运行共享数据库或固定端口。环境变量覆盖至少支持 `AI_PROVIDER`、`HARNESS_SCENARIO`、`HARNESS_SEED`、`HARNESS_RUN_ID` 和 `HARNESS_KEEP_ARTIFACTS`。

## 6. Mock AI 契约

Mock AI 必须实现与真实 OpenAI 兼容适配器相同的业务接口。业务服务只依赖抽象适配器，不得在测试中直接注入数据库记录或跳过 API。

### 6.1 场景文件

首版至少提供：

```text
harness/fixtures/ai/
  jd_parse_success.json
  jd_parse_conflict.json
  assessment_follow_up.json
  assessment_complete.json
  invalid_schema.json
  timeout.json
```

每个场景包含：

- `name` 和 `description`；
- 业务请求类型；
- 可选的输入 fixture ID；
- 合法结构化返回值或故障类型；
- 延迟或超时行为；
- 允许重试次数；
- 预期事件、状态或错误码。

Mock 返回值必须经过与真实模型相同的 Schema 验证。`invalid_schema` 必须真正触发验证错误，`timeout` 必须经过真实的超时/重试路径，而不是在测试代码中直接抛出已处理的最终异常。

### 6.2 允许的故障类型

- 超时；
- 网络/供应商错误；
- 无效 JSON；
- Schema 枚举或范围越界；
- 证据片段不在原文中；
- 空追问或越权能力引用。

故障场景必须验证：用户原回答仍保留、状态不被错误推进、可重试、不会重复创建轮次或事件。

## 7. Fixture 与测试隔离

每次运行创建独立 `RunContext`，至少包含：

```text
run_id
scenario
seed
temporary_directory
database_url
backend_url
frontend_url
started_at_utc
```

固定 fixture 至少包含：

- 两份可以合并的 JD；
- 一份存在能力冲突的 JD；
- 一个已确认模型快照；
- 正常完成测评的回答序列；
- 触发追问、暂停、恢复和重试的回答序列；
- 部分完成的测评；
- 重复幂等键；
- 无效 AI 输出和超时。

测试必须使用固定种子、UTC 时间和稳定 ID 生成策略。临时数据库不可复用于下一次运行，测试不得依赖真实用户数据、真实 API Key 或外部网络。

## 8. 进程生命周期与清理

`demo` 和 `e2e` 的执行流程固定为：

```text
doctor
→ 创建 RunContext
→ 创建临时配置和数据库
→ 启动后端
→ 等待 /api/health
→ 启动前端
→ 等待前端健康地址
→ 执行测试
→ 收集日志、截图和结果
→ 成功清理；失败保留现场
```

要求：

- 记录每个由 Harness 启动的 PID 或进程句柄；
- 只终止本次运行启动的进程，不按端口或进程名误杀用户服务；
- 处理 Ctrl+C、子进程提前退出、健康检查超时和总超时；
- 成功运行默认删除临时目录；失败运行默认保留并在报告中打印绝对路径；
- 清理失败不得覆盖原始测试退出码，但必须进入报告。

## 9. 验证矩阵

### 9.1 单元和领域测试

覆盖解析器、Schema、状态机、权重计算、证据引用、幂等和版本不可变性。AI Mock 只在需要测试适配器边界时出现，领域规则不得依赖模型文案。

### 9.2 契约测试

验证 FastAPI 响应与 TypeScript 类型的关键字段一致，至少覆盖：

- 健康检查；
- 项目与模型版本；
- 测评会话和轮次；
- 证据包；
- 错误码、重试标记和状态枚举。

接口字段变更必须同步更新 Pydantic schema、TypeScript 类型、fixture 和契约测试。

### 9.3 E2E 测试

至少覆盖：

- 阶段一：添加 JD、解析、查看证据、处理冲突、确认冻结；
- 阶段二：开始、回答、追问、暂停、刷新、恢复、重复提交和完成；
- 失败恢复：超时或无效结构化输出后保留回答、显示重试并回到原能力项；
- 阶段边界：未确认模型不能开始阶段二，阶段二不显示正式评分；
- 窄屏：工作台抽屉、焦点返回、Escape 关闭和无横向滚动。

E2E 不逐字比较动态 Agent 文案，而比较服务端状态、事件、证据、恢复动作和页面关键可访问语义。

## 10. 报告与脱敏

每次运行生成：

```text
harness/reports/<run-id>/
  summary.json
  summary.md
  config.redacted.json
  backend.log
  frontend.log
  test-results/
  screenshots/
  traces/
```

`summary.json` 至少包含命令、版本、场景、耗时、每个检查项状态、退出码、失败分类和 artifact 路径。报告中的请求/响应只保留脱敏摘要，不写入 API Key、Authorization、完整 JD、简历、完整用户回答或个人身份信息。

失败分类固定为：`ENVIRONMENT`、`HARNESS`、`APPLICATION`、`CONTRACT`、`E2E`、`TIMEOUT`、`CLEANUP`、`NOT_IMPLEMENTED`。

## 11. CI 设计

GitHub Actions 首版包含两个 Job：

### `backend-and-contract`

- 安装 Python 依赖；
- 执行 Harness doctor；
- 运行 pytest 和契约测试；
- 上传失败报告与后端日志。

### `frontend-and-e2e`

- 安装 Node 依赖和 Playwright 浏览器；
- 运行前端组件测试和生产构建；
- 使用 Mock AI 启动后端/前端并执行 Playwright；
- 上传截图、trace、日志和 Harness 摘要。

真实模型调用不得成为合并门禁。真实模型实验只能通过手动触发、非阻塞的独立任务运行，并且必须使用脱敏数据。

## 12. 错误处理与退出码

建议退出码：

| 退出码 | 含义 |
|---:|---|
| `0` | 所有要求的检查通过 |
| `2` | 参数或配置错误 |
| `3` | 环境依赖缺失 |
| `4` | Harness 编排或清理失败 |
| `10` | 后端/前端单元测试失败 |
| `11` | 契约测试失败 |
| `12` | E2E 或浏览器流程失败 |
| `13` | 超时或进程异常退出 |
| `20` | 当前阶段尚未实现 |

`--keep-going` 结束时返回最高优先级失败码，并在报告中保留全部检查结果。

## 13. 分阶段实施

### 阶段 H1：CLI 与环境自检

- 建立 Python CLI、配置加载、RunContext、退出码和 `doctor`；
- 增加 PowerShell 薄包装；
- 为命令解析、配置覆盖和缺失依赖编写测试。

### 阶段 H2：Mock AI 与测试夹具

- 定义适配器接口和场景 Schema；
- 添加成功、冲突、追问、完成、无效输出和超时 fixture；
- 实现固定种子、稳定 ID、临时 SQLite 和脱敏配置。

### 阶段 H3：测试编排与报告

- 接入 pytest、前端测试、构建和 `git diff --check`；
- 实现进程启动、健康检查、超时、清理和 artifact 收集；
- 生成 JSON/Markdown 摘要。

### 阶段 H4：浏览器验收与 CI

- 接入 Playwright 和关键阶段流程；
- 增加失败恢复、重复提交、阶段边界和窄屏用例；
- 创建两个 GitHub Actions Job；
- 在当前已实现业务范围内启用 `verify` 门禁。

### 阶段 H5：与阶段四质量评估衔接

- 复用场景、RunContext、报告和失败分类；
- 增加 10–20 个脱敏岗位测试集；
- 增加 Prompt 版本对比和人工参考结果；
- 不改变开发验证 Harness 的确定性门禁语义。

## 14. 验收标准

Harness 设计落地后必须满足：

- Windows 上可通过 PowerShell 完成自检、单层测试、完整验证和演示；
- CI 不依赖真实模型 API Key 即可执行核心门禁；
- 同一 `run_id` 和 seed 能得到相同 Mock AI 行为和稳定测试数据；
- Mock AI 走真实适配器、API、状态机和数据库路径；
- 失败测试保留可定位的日志、截图/trace、配置摘要和临时数据库路径；
- 中断、超时和失败不会遗留 Harness 自己启动的服务进程；
- 重复提交、错误恢复、版本冻结、证据追溯和阶段边界都有自动化验证；
- 运行报告不泄露密钥、完整 JD、简历或用户回答；
- 目录尚未实现时明确报告 `NOT_IMPLEMENTED`，不伪造通过；
- `verify` 的退出码可被 CI 正确识别，且本地与 CI 使用同一 Python 编排逻辑。

## 15. 与现有项目规格的关系

本 Harness 遵循：

- `AGENTS.md` 的开发、测试、安全和证据追溯约束；
- `design/00-全局交互基线设计.md` 的统一外壳、事件和响应式规则；
- 阶段一、阶段二和阶段三规格中的状态、版本、证据和阶段边界；
- `docs/superpowers/plans/2026-09-09-full-implementation-roadmap.md` 的跨阶段实施顺序。

Harness 不能通过修改测试来降低业务规格要求。若实际实现与规格不一致，应报告差异并修改实现或规格，而不是把期望值改成当前错误行为。
