# JD 提取、权重与系统提示实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 支持浏览器主动提取和链接抓取 JD，并为模型权重编辑与所有写操作提供独立系统提示。

**Architecture:** 浏览器提取通过本地 localhost 接收端写入现有 JD 文本接口；链接提取继续由后端安全抓取并统一进入材料流程。能力权重在单份 JD 和总模型分别编辑，保存时由后端按同一模型范围归一化；系统提示作为独立 UI 区域读取审计事件，不混入 Agent 消息。

**Tech Stack:** FastAPI、SQLAlchemy、React、TypeScript、Vitest、Playwright。

**Spec:** 用户确认的对话系统提示、双入口 JD 提取和双模型权重归一化要求。

## Global Constraints

- 不绕过登录、验证码或站点访问控制；浏览器提取必须由用户主动触发。
- API Key 只由后端本地配置持有。
- 已确认模型不可修改；权重范围必须为 0-1，归一化和状态校验由后端负责。
- 系统提示使用独立文本框，Agent 自然语言仍进入对话时间线。

### Task 1: 权重编辑与归一化

**Files:** 后端 competency API、前端模型卡片、对应测试。

- [ ] 写失败测试：PATCH 能力接受 weight，保存后同一模型范围权重和为 1；前端编辑卡片提交名称和权重。
- [ ] 实现后端权重校验、归一化和返回字段。
- [ ] 实现两个模型组件的权重输入与提交回调。
- [ ] 运行后端和前端相关测试。

### Task 2: 独立系统提示

**Files:** 审计事件查询接口、App/提示组件、对应测试。

- [ ] 写失败测试：模型写操作后出现独立系统提示，不产生 Agent 消息。
- [ ] 增加项目审计事件读取接口和独立提示列表。
- [ ] 将新增、编辑、删除、权重修改、解析、聚合、冻结结果写入提示列表。
- [ ] 验证刷新后可恢复提示。

### Task 3: 双入口 JD 提取

**Files:** `integrations/jd-extraction` 复制内容、localhost 接收桥、MaterialDialog、后端接口和测试。

- [ ] 只复制源代码、文档和必要配置，排除 `node_modules`、浏览器用户数据和密钥。
- [ ] 增加浏览器主动 POST 的 localhost 接收端，校验来源、长度和字段。
- [ ] 将接收内容绑定到当前项目 JD 导入流程。
- [ ] 保留并加固公开链接抓取，统一返回标题、正文和来源。
- [ ] 添加 API、前端和端到端测试。

### Verification

- [ ] `python -m pytest backend/tests -q`
- [ ] `npm --prefix frontend run test -- --run`
- [ ] `npm --prefix frontend run test:e2e`
- [ ] `npm --prefix frontend run build`
- [ ] `git diff --check`
