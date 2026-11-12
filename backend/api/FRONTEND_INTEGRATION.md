# 前端联调入口（2026-11-13 计划）

> 本文件是前端同学联调时的**唯一入口**。深入细节按链接跳转，不要先通读全部后端文档。
> 状态基线：2026-11-12 本机冒烟通过——提交→1 秒内 `SUCCEEDED`（verdict=AUTO_PASS）→报告 `READY`→PDF 62 KB 下载校验通过。

## 0. 明日联调范围（对齐结论，先读这段）

**只联调这一条链**：前端表单 → `POST /tasks` → 轮询 `GET /tasks/{id}` → `GET /tasks/{id}/report` 下载 PDF。

当前后端**没有**的能力（联调时不要尝试、不要等待）：

| 能力 | 状态 | 明日降级方案 |
| --- | --- | --- |
| 文件上传 / PDF 解析 / Vision 抽取 | 无接口 | 前端表单直接产出结构化 JSON 提交 |
| AuditSession 会话管理 / 用户鉴权 | 无接口 | `session_id` 由前端 `crypto.randomUUID()` 生成占位 |
| WebSocket `/ws/audit/{id}` | 未实现 | HTTP 轮询（契约见下） |
| 跨源研判、最终裁决汇总 | 未实现 | 前端按 `result.verdict` 三态直接展示 |

## 1. 起服务（两条命令，缺一不可）

```bash
# 终端 1：API（另起一个独立终端窗口，不要依赖任何工具的后台会话——联调期间进程可能被回收）
uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# 终端 2：Worker（不启动则任务永远 PENDING）
uv run python -m backend.workers.rule_tasks
```

> 两条也有 Makefile 别名 `make dev` / `make worker`，但**本机 shell 未装 make**，请以原始命令为准。

前置：根目录 `.env` 已配好 `RULE_TASK_ENCRYPTION_KEYS`（**API 与 Worker 必须在同一台机、同一份 .env**；他人机器需要联调须复制同一密钥并共享同一数据库/规则快照，见 [RULE_TASKS_API.md](RULE_TASKS_API.md) §队友接入）。迁移已在 head：`20261108_pdf_reports`。

## 2. 接口速查

| 步骤 | 请求 | 关键点 |
| --- | --- | --- |
| 提交 | `POST /api/v1/rule-engine/tasks`，Header `Idempotency-Key: <UUID，16–128位 [A-Za0-9_-]>` | 成功返回 **202** + `Location`；body ≤ **1 MiB**；未知字段直接 422；可选字段**不要传显式 null，省略即可** |
| 轮询 | `GET /api/v1/rule-engine/tasks/{task_id}` | 活动态 `poll_after_ms=500`、HTTP `Retry-After: 1`；终态 `poll_after_ms=0` 停止轮询 |
| 报告 | `GET /api/v1/rule-engine/tasks/{task_id}/report` | 仅当 `report_status=READY` 才可下载；响应头含 `X-Report-SHA256`（CORS 已 expose） |

**幂等规则**：传输重试必须用**同键同 body**；换键重发会创建新任务。用户改数据后再提交必须换新键，否则 409。

**状态语义（最容易踩的坑）**：

- HTTP 200 ≠ 成功，`SUCCEEDED` ≠ `AUTO_PASS`。终态看 `status`，裁决看 `result.verdict`（`AUTO_PASS` / `NEED_USER_FIX` / `MANUAL_TRIAGE`）。
- `result` 在 SUCCEEDED 时即完整可用，**不必等 PDF**；`report_status` 是独立生命周期（PENDING/RUNNING/READY/FAILED）。
- FAILED 是执行失败（`error.code`：`TASK_EXECUTION_FAILED` / `TASK_DEADLINE_EXCEEDED` 等），与业务裁决无关，前端应新建任务重试而不是展示"审核不通过"。

错误码详表见 [RULE_TASKS_API.md](RULE_TASKS_API.md) §3；机器可读契约为 [openapi.json](openapi.json)（仅公开面三接口）或运行时 `/docs`。响应字段定义在 [schemas/rule_tasks.py](schemas/rule_tasks.py) `TaskResponse`。

## 3. 可直接提交的四份样例

| 文件 | 内容 | 2026-11-12 实测 |
| --- | --- | --- |
| [crs-individual-task-request.json](../../assets/crs-templates/crs-individual-task-request.json) | 个人 HK 完整嵌套契约 | 202 → SUCCEEDED → **AUTO_PASS** → PDF 62 KB ✓ |
| [crs-entity-task-request.json](../../assets/crs-templates/crs-entity-task-request.json) | 实体（Passive NFE + 控权人） | 202 → SUCCEEDED → **MANUAL_TRIAGE**（1 条 WARNING）→ report READY ✓ |
| [crs-controlling-person-task-request.json](../../assets/crs-templates/crs-controlling-person-task-request.json) | 控权人 | 202 → SUCCEEDED → **MANUAL_TRIAGE**（2 条 WARNING）→ report READY ✓ |
| [crs-individual-need-user-fix-task-request.json](../../assets/crs-templates/crs-individual-need-user-fix-task-request.json) | 个人（校验位错误 HKID） | 202 → SUCCEEDED → **NEED_USER_FIX**（2 条 BLOCKER：`INVALID_TIN`、`HK_TIN_IDENTITY_MISMATCH`）→ report READY ✓ |
| 旧平铺单税籍格式 | 兼容保留 | 新接入勿用 |

三种裁决展示态现已全部有现成样例。样例内的 `tin` 为 `A123456(9)`（校验位错误），与 `hk_identity` 形成双 BLOCKER，可一并联调多问题卡片渲染。

另：`validation` 内可选 `include_guidance: true` 才触发 AI 补正文案（`result.guidance.status=GENERATED`，`model=qwen-plus`，约 4.3s）；不带该字段时 `guidance.status=NOT_REQUESTED`，`result.explanation_cards` 仍由规则层固定文案生成，前端两种形态都需能渲染。

提交时替换 `session_id` 为新 UUID、`policy.today` 为当日、按需带 `deadline_at`（整条链路剩余截止，非重新计 30 秒）。`Idempotency-Key` 每次真实审核用新随机键。

curl 冒烟（Windows Git Bash 可用，注意 httpx/代理无关，curl 不受影响）：

```bash
curl -i http://localhost:8000/api/v1/rule-engine/tasks \
  -H 'Content-Type: application/json' \
  -H "Idempotency-Key: $(python -c 'import uuid;print(uuid.uuid4().hex)')" \
  --data-binary @assets/crs-templates/crs-individual-task-request.json
```

## 4. 跨机访问与 CORS

前端 dev server 在别的机器时：API 已监听 `0.0.0.0:8000`，用 `http://<后端机IP>:8000`（建议前端走 Vite proxy），并把该前端 origin（如 `http://localhost:5173` 或 `http://<ip>:5173`）加进后端 `.env` 的 `CORS_ORIGINS` 后重启 API。当前已含 `http://localhost:3000` 与 `http://localhost:5173`。

## 5. 排障速查

| 现象 | 最可能原因 | 处理 |
| --- | --- | --- |
| 一直 `PENDING` 不转 `RUNNING` | Worker 没起 / Worker 与 API 的 `.env` 加密密钥不一致 | 起 Worker；核对 `RULE_TASK_ENCRYPTION_KEYS` |
| 提交 503 `TASK_ENCRYPTION_UNAVAILABLE` | `.env` 缺密钥 | 生成 Fernet key 写入后同时重启 API+Worker |
| 提交 422 `VALIDATION_ERROR` | 传了未知字段或显式 `null` | 省略可选字段；对照 openapi.json `TaskRequest` |
| 提交 409 `IDEMPOTENCY_CONFLICT` | 同键换了 body | 换新键 |
| report 下载 409 `REPORT_GENERATING` | 报告还没 READY | 按 `Retry-After: 2` 继续轮询任务状态 |
| 任务 FAILED 且 `error.code=TASK_BUILD_MISMATCH` | API 与 Worker 跑的代码版本不一致（后端改代码后只重启了一边） | 后端把 API 与 Worker **同时**重启，前端新建任务重发 |
| 任务卡 PENDING 直到超时 | deadline 传了过期值 | `deadline_at` 必须是带时区的未来 RFC3339 |

## 6. 给前端同学的范围声明（可直接转发）

> 明天联调只走"结构化 JSON → 提交任务 → 轮询 → 下载 PDF"三接口链。后端当前没有文件上传/Vision 抽取/WebSocket/会话管理接口，表单侧请直接用四份样例 JSON 的字段结构做表单（个人/实体/控权人三类，其中个人另有 NEED_USER_FIX 校验位错误变体，见 backend/api/FRONTEND_INTEGRATION.md §3）。注意三点：① 提交必须带 `Idempotency-Key`（每轮新审核用新 UUID，传输重试用同键同 body）；② `status=SUCCEEDED` 后要再看 `result.verdict` 三态展示，HTTP 200 不代表通过；③ PDF 要等 `report_status=READY` 再拉，规则结果本身不用等。后端机器起两条命令（两个独立终端）：`uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000` 和 `uv run python -m backend.workers.rule_tasks`，Worker 没起任务会永远 PENDING。
