# 异步规则引擎接入

主后端调用两个接口：提交结构化表单，再按 task_id 查询执行状态和完整结果。
另有前端 PDF 下载接口，见 [报告 API](PDF_REPORT_API.md)；前三者构成当前三条公开接口。
`session_id` 是主流程的审核会话 UUID，`task_id` 是规则引擎一次校验的 UUID；补正后提交新任务。
用户鉴权、会话归属校验、文件抽取、跨源研判和最终 AuditSession 状态仍由主后端负责。
这里是内部服务接口，不能直接作为公网匿名接口开放。

## 1. 提交任务

```http
POST /api/v1/rule-engine/tasks
Content-Type: application/json
Idempotency-Key: 8d766b51-283f-445c-967c-35ee0df64681
```

```json
{
  "session_id": "efbca71a-c7c4-4cf7-9cf5-d557fe8cf334",
  "validation": {
    "form_data": {
      "holder_name": "DEMO",
      "holder_dob": "1990-05-20",
      "residence_address": "Demo Building, Hong Kong",
      "jurisdiction_code": "HK",
      "holder_type": "INDIVIDUAL",
      "tin_type": "HKID",
      "tin": "A123456(3)",
      "has_no_tin": false,
      "has_signature": true,
      "signing_date": "2026-11-04"
    },
    "policy": {"today": "2026-11-08"},
    "indicia_issues": [],
    "include_guidance": false
  }
}
```

上例号码为合成测试数据。新接入优先使用完整嵌套结构，三份可直接提交的样例：

- [个人任务](../../assets/crs-templates/crs-individual-task-request.json)
- [实体任务](../../assets/crs-templates/crs-entity-task-request.json)
- [控权人任务](../../assets/crs-templates/crs-controlling-person-task-request.json)

| 字段 | 约束 |
| --- | --- |
| session_id | 必填 UUID；由主流程创建，不由规则引擎生成 caseNum |
| validation | 原 ValidationRequest 完整结构；支持新嵌套／旧单税籍／旧多税籍 |
| deadline_at | 可选 RFC3339 带时区时间，建议传主审核开始时间 + 30 秒 |
| Idempotency-Key | 必填随机不透明键，16–128 个字母、数字、下划线或连字符；推荐 UUID，不含姓名/TIN |

`validation` 的字段约束、日期和事实来源见 [结构化契约](STRUCTURED_CRS_API.md)。
最大请求体 1 MiB；未知字段拒绝；新结构不接受显式 null 的可选字段，应省略它们。
`policy.today` 是业务日期，`deadline_at` 是运行截止时间，两者用途不同。
结构校验错误立即返回 422；缺签、TIN 错误等业务问题在 Worker 中执行并生成正常结果。

事务成功后返回 **202 Accepted**，`Location` 指向查询接口，`Retry-After: 1`，`Cache-Control: no-store`。
响应包含 task_id、session_id、status、created_at、deadline_at、expires_at、started_at、completed_at、
rule_version_id、rule_revision、engine_build_id、poll_after_ms、report_status、report_error、report_url、result、error。
初始通常为 PENDING，result/error 为 null；并发 Worker 可能已开始执行。

同键同输入重试返回同任务，包括已经完成的结果；规则热更新不会让旧键重新执行。
同键不同输入返回 409，补正数据必须使用新键。原请求省略 deadline_at 时，重试不会重新开始旧任务计时。
幂等比较包括 session_id、显式 deadline_at 和完整 validation。
连接断开或提交超时可能无法确定提交是否成功，必须用原键和原 body 重试，不能换键盲目重建。

## 2. 查询状态和结果

```http
GET /api/v1/rule-engine/tasks/{task_id}
```

HTTP 200 返回同一任务响应结构：

| status | result / error | 上游动作 |
| --- | --- | --- |
| PENDING | null / null | 等待排队，按建议继续轮询 |
| RUNNING | null / null | 正在执行，按建议继续轮询 |
| SUCCEEDED | 完整 ValidationResponse / null | 消费规则结果，继续主流程 |
| FAILED | null / 固定错误码和安全提示 | 停止轮询；由主流程处理执行失败，必要时新建任务 |

活动任务 `poll_after_ms=500`，HTTP `Retry-After=1` 秒；客户端建议至少每秒一次，可增加随机抖动。
终态 `poll_after_ms=0`。**HTTP 200 或 SUCCEEDED 不等于 AUTO_PASS**：
SUCCEEDED 的 result.verdict 仍可能是 NEED_USER_FIX 或 MANUAL_TRIAGE。
校验 SUCCEEDED 后后台预生成报告，report_status 为 PENDING/RUNNING/READY/FAILED。仅 READY 时 report_url 有值，report_error 表示最终生成错误；规则 result 无需等待 PDF。主后端将状态和地址传给前端，前端只调用 PDF GET。
完整结果保留逐项检查、问题来源、执行范围、规则/表单策略版本、输入指纹及可选 guidance。
AI 不可用时现有确定性降级继续有效；Agent 不改变规则裁决，不负责资料提取。

主流程通过 `run_audit_pipeline()` 编排这些调用，更新自己的 AuditSession 和 WebSocket 步骤状态。
规则引擎不直接写主会话，不要求上游查数据库，不新增主流程最终裁决接口；第三条 report 只把已保存的规则结果导出 PDF。

## 3. 截止、恢复和错误

实际截止为 min(上游 deadline_at, 接收时刻 + RULE_TASK_TIMEOUT_SECONDS)，默认上限 30 秒。
排队、执行、模型等待与结果保存都消耗同一任务预算；提交等待也受截止/服务器上限约束。
必须传整条链路的剩余截止时间，不能在 Vision 完成后重新计满 30 秒。
数据库提交和调度不提供硬实时保证；提交超时存在提交结果不确定性，按同键重试处理。

| HTTP / code | 含义 |
| --- | --- |
| 404 TASK_NOT_FOUND | UUID 格式正确但不存在 |
| 409 IDEMPOTENCY_CONFLICT | 幂等键输入冲突 |
| 410 TASK_EXPIRED | 超出保留时间；不返回旧表单/结果，同键不重新执行 |
| 413 REQUEST_TOO_LARGE | 请求超过 1 MiB |
| 422 VALIDATION_ERROR / TASK_DEADLINE_INVALID | 结构、字段或截止时间无效；错误不会回显原始值 |
| 503 TASK_ENCRYPTION_UNAVAILABLE | 未配置有效任务加密密钥 |
| 503 TASK_QUEUE_FULL | 活动任务数量已满 |
| 503 TASK_SUBMISSION_TIMEOUT | 提交等待超时，使用原键重试 |
| 503 NO_ACTIVE_RULES / RULE_ENGINE_UNAVAILABLE | 活动规则或存储不可用 |

503 带 Retry-After。FAILED 的 error.code 包括 TASK_EXECUTION_FAILED、TASK_BUILD_MISMATCH、
TASK_DEADLINE_EXCEEDED、TASK_DEADLINE_OR_ATTEMPTS_EXCEEDED；异常正文不存储、不返回。
租约期限不超过 deadline；期限已到的 RUNNING 任务由下一次 Worker 扫描转 FAILED。
Worker 未运行时任务不会执行或自动转终态，上游必须依据自己的 deadline 停止轮询并标记主流程异常。

Worker 崩溃后租约过期可重领，默认最多 3 次尝试。
采用至少一次尝试和带 token 的终态提交；不能承诺计算恰好执行一次。
已丢失租约的 Worker 无法覆盖新结果。取消线程等待不会强行终止 Python 线程；核心计算无写副作用。

## 4. 队友调用示例

```bash
curl -i http://localhost:8000/api/v1/rule-engine/tasks \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: 8d766b51-283f-445c-967c-35ee0df64681' \
  --data-binary @assets/crs-templates/crs-individual-task-request.json

# 用上一步 Location 的实际 task_id
curl http://localhost:8000/api/v1/rule-engine/tasks/实际task_id
```

实际业务调用时，修改样例 session_id、policy.today 并追加整条审核剩余的 deadline_at。
相同样例复用同一幂等键属于重试；新的审核必须使用新的随机键。

```python
import asyncio
from datetime import datetime, timezone
from uuid import uuid4
import httpx

async def validate_form(session_id: str, validation: dict, deadline_at: datetime) -> dict:
    key = str(uuid4())  # 传输重试期间保存并复用该键和 body。
    body = {"session_id": session_id, "deadline_at": deadline_at.isoformat(), "validation": validation}
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=5) as client:
        accepted = await client.post("/api/v1/rule-engine/tasks", json=body, headers={"Idempotency-Key": key})
        accepted.raise_for_status()
        location = accepted.headers["Location"]
        while datetime.now(timezone.utc) < deadline_at:
            response = await client.get(location)
            response.raise_for_status()
            task = response.json()
            if task["status"] == "SUCCEEDED":
                return task["result"]
            if task["status"] == "FAILED":
                raise RuntimeError(task["error"]["code"])
            await asyncio.sleep(max(1, task["poll_after_ms"] / 1000))
    raise TimeoutError("Main audit deadline exceeded")
```

示例只展示正常提交/轮询；生产调用在客户端保存 key/body，并针对传输失败或 503 做有界同键重试。
不要把 error 当规则 AUTO_PASS，也不要把空 indicia_issues 当作跨源检查已经完成。

## 5. 配置和启动

详细设计见 [异步任务设计](../engine/ASYNC_TASKS.md)，新库初始化与已有库升级见 [数据库说明](../infrastructure/db/README.md)。
完整 validation_engine.sql 为十表快照；推荐新库 bootstrap_rules.sql + Alembic，已有库只升级迁移，不重复执行 SQL。先 `uv sync --frozen`，设置数据库并升级迁移：

```bash
# 已有基础规则表和 20261103_rule_history 迁移的环境
uv run alembic upgrade head

# 生成标准 Fernet 密钥，安全写入本地环境，不要提交
uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

配置 `.env` 中 `RULE_TASK_ENCRYPTION_KEYS=["生成的密钥"]`，首项为当前加密键，后续为旧键。
API 与 Worker 必须使用相同数据库、密钥列表、代码和 Python/依赖版本。
轮换时先让两者都加载 `[new, old]`；旧键至少保留到旧任务全部过期和清理后。
删除旧键过早会使结果无法解密或同键匹配失败。

```bash
# 终端一：API 两连接；不要再增加 uvicorn worker 进程突破连接预算
DATABASE_POOL_SIZE=2 DATABASE_MAX_OVERFLOW=0 uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000

# 终端二：独立 Worker，运行时连接池固定为 1
uv run python -m backend.workers.rule_tasks

# 单次领取／手动清理全部已过期密文
uv run python -m backend.workers.rule_tasks --once
uv run python -m backend.workers.rule_tasks --cleanup
```

API 2 + Worker 1 合计最多 3 个连接；迁移/更新任务应避免同时额外占用预算。
Worker 不持有连接等待规则计算或模型响应。数据库暂时不可用时常驻 Worker 脱敏记录并重试。
默认容量 100、服务器任务上限 30 秒、保留 86400 秒、租约 5 秒、心跳 1 秒、最多 3 次尝试。
对应环境变量均以 RULE_TASK_ 开头，见 `.env.example`。

输入、完整规则/表单策略快照及结果使用 Fernet 认证加密；幂等请求摘要使用 HMAC。
任务 UUID、session_id、状态、时间、版本和不透明幂等键为运行元数据。
到期查询立即 410；Worker 持续运行或 cleanup 才会实际清除密文，保留幂等 tombstone。
旧内部 rule_audit_records 不在此次加密改造范围内；主系统原文件、商户数据等需其自身留存策略。

新接入的 Swagger 展示提交、查询及 PDF 导出三条接口；旧同步 `/validate` 保留兼容、从 OpenAPI 隐藏。
本地 PostgreSQL 迁移及 Worker 隔离集成已验证；云端数据库、百炼联调和生产进程部署仍需在目标环境验收。


## 竞赛解释与补正对比

result 新增 explanation_cards，复用规则／已保存 Agent 证据生成可展示的原因及补正动作，不改变 verdict。
GET task 可附加 compare_to=旧任务UUID，同会话且均成功时返回 comparison；不传时为 null。
完整字段、错误及初始化调用见 [竞赛能力文档](COMPETITION_API.md)。新 PDF 使用模板 v2，已保存旧 PDF 不自动改写。
