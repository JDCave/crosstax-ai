# 规则引擎 HTTP API

规则引擎作为现有 FastAPI 应用的一组内部接口运行，前缀 `/api/v1/rule-engine`。
复用现有 PostgreSQL 连接池、不可变快照、发布规则和审核归档服务，没有第二套引擎或连接池。
队友可在其 `run_audit_pipeline()` 中调用本 API，上传、OCR 和跨源推理仍由其流水线负责。
这些是结构化数据的规则校验端点，不是完整文件审核流水线的新实现。

## 启动与连接

先配置根目录 `.env`，原六表初始化完毕后执行迁移，再启动：

```bash
uv run alembic upgrade head
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

本机地址 `http://localhost:8000`，队友远程调用时替换成服务机器的可达地址。
OpenAPI：`/openapi.json`；交互式文档：`/docs`。
已有 `/health`、`/ready` 的地址和行为保持不变。
本接口未添加认证或用户隔离，按竞赛内部服务部署；主后端负责调用授权和 session_id 的命名空间隔离。
接口不暴露规则注册/审批/激活写操作，发布继续使用原 CLI 和审批门禁。

## 接口列表

| 方法 | 路径（均带上述前缀） | 行为 |
| --- | --- | --- |
| POST | /validations | 校验结构化 JSON 并归档，支持会话幂等 |
| GET | /validations/{session_id} | 读取已存结果，不重新执行 |
| POST | /validations/{session_id}/replay | 使用历史规则、业务日期和构建信息重放 |
| GET | /rules/current | 获取活动规则版本、发布 revision、规则数量 |
| GET | /rules/coverage | 获取主体/标识类型、验证等级和官方来源 |

## 提交请求

```json
{
  "session_id": "merchant-demo-001",
  "form_data": {
    "holder_name": "DEMO PERSON",
    "holder_dob": "1949-12-31",
    "residence_address": "DEMO ADDRESS",
    "jurisdiction_code": "CN",
    "holder_type": "INDIVIDUAL",
    "tin_type": "CN_ID",
    "tin": "11010519491231002X",
    "has_no_tin": false,
    "has_signature": true,
    "signing_date": "2026-11-01"
  },
  "policy": {
    "today": "2026-11-03",
    "earliest_signing_date": null,
    "strict_coverage": true
  },
  "indicia_issues": []
}
```

号码仅作为校验示例，不声称对应真实签发记录。
`session_id` 为 1-100 个 ASCII 字母、数字、下划线、点、连字符，首字符为字母或数字。
业务日期必须由主后端明确提供，最早签署日期不能晚于业务日期。
新版规则要求按覆盖接口提供正确的 holder_type/tin_type；缺失类型会进入复核。
indicia_issues 可省略，最多 100 条，必须符合共享 AuditIssue 契约；此处不自行调用大模型。
请求体最多 1 MiB（按实际接收字节检查，不依赖 Content-Length）。

## 响应与幂等

返回 `{"session_id":"...","result":{...}}`，result 是完整 ValidationResult：
规则版本/revision、form_issues、indicia_issues、verdict、tin_check 和 execution。

- HTTP 200 代表服务成功完成或返回已存校验，三种业务 verdict 均为 200。
- tin_check 说明实际检查、未检查、来源、规则 ID 和失败原因，前端不要把 FORMAT_ONLY 显示成完整验证。
- 相同 session_id、相同表单/策略/上游问题返回第一次已提交结果，即使当前规则已更新。
- 相同 ID 不同输入返回 409；重新审核应使用新的 session_id。
- 结果响应不包含原始表单，但数据库归档仍保存表单用于重放。
- replay 是独立操作；不把 GET 查询结果混同为使用当前规则重新审核。

## 错误协议

规则引擎接口的错误使用 `{"code":"...","message":"..."}`，不会回显 Pydantic 原始输入或数据库错误详情。

| HTTP | 代码 | 含义 |
| --- | --- | --- |
| 404 | NOT_FOUND | 会话结果不存在 |
| 409 | CONFLICT | 会话输入冲突或历史构建/输入/规则无法一致重放 |
| 413 | REQUEST_TOO_LARGE | 请求体超过 1 MiB |
| 422 | VALIDATION_ERROR | JSON、类型、字段或日期策略结构错误 |
| 503 | NO_ACTIVE_RULES | 没有可用的活动规则 |
| 503 | RULE_ENGINE_UNAVAILABLE | 数据库或规则数据异常 |
| 500 | INTERNAL_ERROR | 其他未预期错误，由原应用错误层处理 |

未匹配路由、HTTP 方法等框架级错误仍按现有应用默认行为，不改变队友其他接口。

## Python 调用示例

```python
import httpx

async def call_rule_engine(payload: dict) -> dict:
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30) as client:
        response = await client.post("/api/v1/rule-engine/validations", json=payload)
        response.raise_for_status()
        return response.json()
```

网络超时可用同一个 session_id 和相同请求体重试；409 需处理输入冲突，不能无限重试。
队友将返回的完整 result 保存到主 AuditSession，以便与引擎执行信封对账。
本服务归档事务与队友主会话事务相互独立，不宣称跨服务原子提交。

## 验证

HTTP 测试使用真实引擎和隔离数据库，覆盖 Case A-E、查询/重试/重放、覆盖信息、
冲突/缺失/无效输入、错误脱敏、请求大小限制和系统失败。
另有真实 PostgreSQL 的底层归档/迁移/并发测试；没有要求队友改动其业务路由。
