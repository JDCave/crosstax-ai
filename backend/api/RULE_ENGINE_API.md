# 规则引擎 API：传入数据，返回校验结果

队友只需调用一次：

```http
POST /api/v1/rule-engine/validate
Content-Type: application/json
```

接口同步执行当前活动规则，直接返回结果。无需 session_id、创建会话、轮询、查询规则或调用重放。
HTTP 调用只读取规则，不保存表单和审核结果；主后端负责自己的会话与持久化。
之前的 /validations、结果查询、重放、current、coverage HTTP 路由已移除。
规则维护和历史重放保留为内部 Python/CLI 能力，和队友的校验调用相互独立。

## 启动

已有规则表和活动版本后，启动现有 FastAPI 应用：

```bash
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

本机 Base URL 为 `http://localhost:8000`；远程调用替换为服务机器可达地址。
`/docs` 为交互文档，`/openapi.json` 为实时契约，[openapi.json](openapi.json) 为仓库快照。
已有 `/health` 和 `/ready` 保留。当前为内部服务接口，无新增认证机制。

## 请求示例

```json
{
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
    "today": "2026-11-03"
  },
  "indicia_issues": []
}
```

号码只作为校验示例，不代表真实签发记录。
顶层必填 `form_data`、`policy`；`indicia_issues` 可省略，默认空数组。
日期由主后端明确提供以便重现，不由服务主机的时区或日期自动替换。
顶层/form_data 不接受未知字段，form_data 布尔值须为 JSON true/false，不能用字符串。
请求体最大 1 MiB，按实际字节检查，超过限制返回 413。

### form_data

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| holder_name | string | 必填，1-300 字符，纯空白产生阻断 |
| holder_dob | string | 必填，最长 32 字符，检查有效 YYYY-MM-DD |
| residence_address | string | 必填，1-2000 字符，纯空白产生阻断 |
| jurisdiction_code | string | 必填，两位大写代码；未覆盖转人工复核 |
| holder_type | INDIVIDUAL / ENTITY / null | 模型可省略；当前正式规则需明确主体类型 |
| tin_type | string / null | 最长 100 字符；如 CN_ID、HK_BR、SG_NRIC |
| tin | string / null | 不转数值，保留前导零；原文超过 256 字符产生阻断 |
| has_no_tin | boolean | 必填；和已填 TIN 矛盾会阻断 |
| tin_reason_code | A / B / C / null | 无 TIN 时必填，有 TIN 时不应再填写 |
| tin_reason_explanation | string / null | 最长 4000 字符，Reason B 去除两端空白后至少 5 字符 |
| has_signature | boolean | 必填，缺签阻断 |
| signing_date | string / null | 最长 32 字符，需有效 YYYY-MM-DD 且不晚于 policy.today |

主体/标识类型清单见 [官方规则覆盖文档](../../rules/GLOBAL_COVERAGE.md)，无需额外调用查询 API。

### policy 与上游问题

| 字段 | 默认/要求 |
| --- | --- |
| today | 必填，业务日期 YYYY-MM-DD |
| earliest_signing_date | 可省略/null；指定时不能晚于 today |
| strict_coverage | 默认 true；false 仅影响旧 schema v1 长度兜底，不能关闭 v2 未覆盖复核 |

indicia_issues 最多 100 条，每条含 code、severity（BLOCKER/WARNING）、message、confidence（0-1），field 可为空。
队友没有跨源问题时不传即可；本接口不负责 OCR 或调用模型提取数据。

## 响应

不再包裹 result 或 session_id，直接返回：

```json
{
  "verdict": "NEED_USER_FIX",
  "issues": [
    {
      "code": "INVALID_TIN",
      "severity": "BLOCKER",
      "field": "tin",
      "message": "TIN 校验位或标识类型不符合当前规则。请核对后重新提交",
      "confidence": 1.0
    }
  ],
  "rule_version_id": "<规则内容 SHA-256>",
  "rule_revision": 3,
  "checks": {
    "status": "FAILED",
    "verification_level": "CHECKSUM",
    "rule_id": "<实际命中规则 ID>",
    "source_url": "<官方资料 URL>",
    "algorithm_source_url": null,
    "checks_performed": ["rule_selection", "normalization", "format", "checksum"],
    "checks_not_performed": ["issuance", "ownership", "tax_residency"],
    "reason_code": "CHECKSUM_MISMATCH"
  },
  "execution": {
    "engine_build_id": "<引擎构建指纹>",
    "input_fingerprint": "<表单、策略与上游问题指纹>",
    "policy": {
      "today": "2026-11-03",
      "earliest_signing_date": null,
      "strict_coverage": true
    }
  }
}
```

以上为错误 TIN 的结构示意，哈希、规则 ID 和 URL 用占位符；与前面的通过样例不是同一结果。

- verdict：AUTO_PASS（无问题）、NEED_USER_FIX（任意 BLOCKER）、MANUAL_TRIAGE（只有 WARNING）。
- issues：引擎问题在前、上游问题在后；通过时为空数组。
- checks：实际执行深度、失败原因及规则来源；FORMAT_ONLY 不代表校验位通过。
- 无 TIN 豁免目前只检查声明完整性，适用性待人工复核，不会仅凭 Reason A/C 自动放行。
- 未覆盖法域或标识类型产生 WARNING，不宣称已完成验证。
- rule_version_id/rule_revision：本次使用的规则版本；execution 用于主后端保存执行依据。
- 所有正常业务裁决均为 HTTP 200，调用方必须读取 verdict，不能只用 HTTP 状态判断表单通过。

## 错误

```json
{"code": "VALIDATION_ERROR", "message": "Invalid request JSON or field values"}
```

| HTTP | code | 说明 |
| --- | --- | --- |
| 413 | REQUEST_TOO_LARGE | 请求体过大 |
| 422 | VALIDATION_ERROR | JSON、字段类型或日期策略结构错误 |
| 503 | NO_ACTIVE_RULES | 没有活动规则 |
| 503 | RULE_ENGINE_UNAVAILABLE | 数据库或规则数据不可用 |
| 500 | INTERNAL_ERROR | 未预期系统错误 |

结构错误不回显完整输入，系统错误不回显数据库详情。
格式有效但存在业务问题仍返回 200 + issues。
旧路由或不存在的路径返回框架默认 404。

## 队友调用示例

```python
import httpx

async def validate_form(form_data: dict, business_date: str) -> dict:
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30) as client:
        response = await client.post(
            "/api/v1/rule-engine/validate",
            json={"form_data": form_data, "policy": {"today": business_date}}
        )
        response.raise_for_status()
        return response.json()
```

将请求 JSON 保存为 request.json 后也可使用：

```bash
curl -X POST http://localhost:8000/api/v1/rule-engine/validate \
  -H 'Content-Type: application/json' --data-binary @request.json
```

每次调用使用当时的活动规则；重试不需要会话 ID，但规则更新后结果可能变化。
主后端若需要固定某次结果，应保存自己的请求和本响应，不把重试理解为读取历史记录。
内部归档/重放服务仍保留，但不由这个 HTTP 接口自动调用。
