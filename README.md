# 岗位胜任力测评与人才画像系统

## 阶段二：自适应文字测评

阶段二必须建立在阶段一已确认（`CONFIRMED`）的岗位胜任力模型上。它生成可暂停、可恢复、可追问的文字测评证据。阶段三读取终态证据包和 `ACTIVE` Rubric，生成不可变、可追溯的辅助性能力报告；`INCOMPLETE` 能力不会被当作 0 分。

### API

- `POST /api/projects/{project_id}/assessments` 创建 `READY` 会话
- `POST /api/assessments/{session_id}/start` 开始并生成主问题
- `POST /api/assessments/{session_id}/turns` 提交回答（需 `idempotency_key`）
- `POST /api/assessments/{session_id}/pause`、`/resume`、`/finish`、`/retry`
- `GET /api/assessments/{session_id}` 获取服务端会话快照
- `GET /api/assessments/{session_id}/events` 获取审计事件
- `GET /api/assessments/{session_id}/evidence-package` 获取 `FULL` 或 `PARTIAL` 证据包
- `POST /api/assessment-sessions/{session_id}/reports` 生成报告（需 `idempotency_key`）
- `GET /api/assessment-sessions/{session_id}/reports`、`GET /api/reports/{report_id}` 查看历史版本
- `POST /api/reports/{report_id}/narrative/retry` 重试叙述、`GET /api/reports/{report_id}/scoring-policy` 查看评分规则
- `GET/POST /api/model-versions/{model_version_id}/rubrics` 管理 Rubric；`POST /api/rubric-sets/{id}/activate` 激活版本

### AI 配置与演示

复制 `backend/.env.example` 为 `backend/.env`，按需设置 `DEEPSEEK_API_KEY`、`LLM_BASE_URL` 和 `LLM_MODEL`。未配置 API key 或测试中 mock AI 时，核心流程仍可演示；阶段三基础评分是确定性的，叙述适配器失败会保留基础报告并标记 `PENDING_RETRY`。自动化测试不会访问真实网络。

### 本地验证

```powershell
python -m pytest backend/tests -q
npm --prefix frontend run test
npm --prefix frontend run test:e2e
npm --prefix frontend run build
```
