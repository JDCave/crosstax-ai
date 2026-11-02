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

## 字段契约

顶层必填 `session_id`、`form_data`、`policy`；`indicia_issues` 默认空数组。
顶层和 form_data 不接受未知字段。布尔字段必须使用 JSON true/false，不能传字符串。

| form_data 字段 | 类型 | 要求 |
| --- | --- | --- |
| holder_name | string | 必填，1-300 字符；纯空白产生业务阻断 |
| holder_dob | string | 必填，最长 32 字符；日期无效产生业务阻断 |
| residence_address | string | 必填，1-2000 字符；纯空白产生业务阻断 |
| jurisdiction_code | string | 必填，两位大写法域代码；未覆盖产生人工复核 |
| holder_type | INDIVIDUAL / ENTITY / null | 模型可省略；当前 typed 规则需明确提供以选择规则 |
| tin_type | string / null | 最长 100 字符；按 coverage 中的值提供，不自动猜测 |
| tin | string / null | 不转数值，保留前导零；号码检查限制原文最长 256 字符 |
| has_no_tin | boolean | 必填；与已填 TIN 矛盾时产生业务阻断 |
| tin_reason_code | A / B / C / null | 无 TIN 时必填；有 TIN 时不应再填 |
| tin_reason_explanation | string / null | 最长 4000 字符；Reason B 去除两端空白后至少 5 字符 |
| has_signature | boolean | 必填；false 产生 NO_SIGNATURE |
| signing_date | string / null | 最长 32 字符；需有效 YYYY-MM-DD，不晚于 policy.today |

无 TIN 声明目前只检查完整性，未证明法域豁免适用，因此返回 EXEMPTION_REVIEW_REQUIRED 并进入复核。
结构错误返回 HTTP 422；通过结构验证后发现业务问题返回 HTTP 200 + NEED_USER_FIX/MANUAL_TRIAGE。

| policy 字段 | 类型 | 默认/含义 |
| --- | --- | --- |
| today | YYYY-MM-DD | 必填，由主后端确定的业务日期 |
| earliest_signing_date | YYYY-MM-DD / null | 默认 null；团队确认后可提供最早允许签署日期 |
| strict_coverage | boolean | 默认 true；false 仅保留旧 schema v1 的历史长度兜底，不关闭 v2 未覆盖复核 |

每条 indicia_issues 包含 code、severity（BLOCKER/WARNING）、message、confidence（0-1），field 可为 null。
问题顺序属于已存执行输入的一部分；重试时保持内容及顺序一致。

## 结果字段

| result 字段 | 含义 |
| --- | --- |
| rule_version_id | 实际执行规则内容的 SHA-256 版本 |
| rule_revision | 发布修订号，回滚也递增 |
| verdict | AUTO_PASS / NEED_USER_FIX / MANUAL_TRIAGE |
| form_issues | 完备性、TIN、未覆盖及豁免待复核问题数组 |
| indicia_issues | 上游提供的跨源问题数组 |
| tin_check | 实际检查深度、来源及失败原因 |
| execution | 引擎构建指纹、输入指纹、完整策略；主后端应原样保存 |

`tin_check.status`：PASSED、FAILED、NOT_COVERED、NOT_APPLICABLE。
`verification_level`：NONE、FORMAT_ONLY、CHECKSUM；表示本次实际执行深度。
`checks_performed` / `checks_not_performed` 明确哪些检查运行或没有运行。
NOT_APPLICABLE 只说明本次未执行号码校验，不代表豁免已成立。
`rule_id`、`source_url`、`algorithm_source_url` 在未命中规则时可为 null。
指纹用于一致性核对，不是加密、签名或权限凭证。

## 其他端点的响应

`GET /rules/current`：

```json
{
  "rule_version_id": "<规则内容 SHA-256>",
  "revision": 3,
  "rule_count": 66
}
```

数字仅为当前基线示例，不应硬编码到调用方。

`GET /rules/coverage`：

```json
{
  "rule_version_id": "<规则内容 SHA-256>",
  "revision": 3,
  "rules": [
    {
      "jurisdiction_code": "CN",
      "holder_type": "INDIVIDUAL",
      "tin_type": "CN_ID",
      "rule_id": "CN_CN_ID_INDIVIDUAL",
      "verification_level": "CHECKSUM",
      "source_url": "https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/china-tin.pdf",
      "algorithm_source_url": null
    }
  ]
}
```

上例仅展示一个条目。coverage 的 verification_level 表示规则配置能力，单次结果 tin_check 表示实际执行深度；格式先失败时不会声称已经执行校验位。

查询和重放返回与 POST validations 相同的 `session_id + result` 信封。
重放无需请求体；只支持原构建、历史规则和存档输入一致时执行，否则 409。

## curl 联调

将前面的请求 JSON 保存为 `request.json`：

```bash
curl -X POST http://localhost:8000/api/v1/rule-engine/validations \
  -H 'Content-Type: application/json' --data-binary @request.json
curl http://localhost:8000/api/v1/rule-engine/validations/merchant-demo-001
curl -X POST http://localhost:8000/api/v1/rule-engine/validations/merchant-demo-001/replay
curl http://localhost:8000/api/v1/rule-engine/rules/current
curl http://localhost:8000/api/v1/rule-engine/rules/coverage
```

完整机器可读字段、必填项、枚举与响应模型见 [OpenAPI 快照](openapi.json)。


## 校验成功响应示例

下例展示完整信封结构，哈希为占位符，具体规则版本、修订号和指纹以运行结果为准。

```json
{
  "session_id": "merchant-demo-001",
  "result": {
    "rule_version_id": "<规则内容 SHA-256>",
    "rule_revision": 3,
    "execution": {
      "engine_build_id": "<引擎构建指纹>",
      "input_fingerprint": "<表单、策略与上游问题的指纹>",
      "policy": {
        "today": "2026-11-03",
        "earliest_signing_date": null,
        "strict_coverage": true
      }
    },
    "tin_check": {
      "status": "PASSED",
      "verification_level": "CHECKSUM",
      "rule_id": "CN_CN_ID_INDIVIDUAL",
      "source_url": "https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/china-tin.pdf",
      "algorithm_source_url": null,
      "checks_performed": [
        "rule_selection",
        "normalization",
        "format",
        "checksum"
      ],
      "checks_not_performed": [
        "issuance",
        "ownership",
        "tax_residency"
      ],
      "reason_code": "CHECKS_PASSED"
    },
    "form_issues": [],
    "indicia_issues": [],
    "verdict": "AUTO_PASS"
  }
}
```
