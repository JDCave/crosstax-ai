# CRS 表格校验接口：队友接入说明

> 2026-11-08：同步后的嵌套新契约已接入，个人／实体／控权人及流程边界见 [结构化 CRS 接入说明](../../backend/api/STRUCTURED_CRS_API.md)。下方保留旧格式兼容说明；旧版 20 行限制不适用于新结构。

主后端提交结构化数据，一次调用同步返回规则校验结果和可选 AI 补正建议。
接口不负责 PDF/OCR/字段提取，不保存表单和结果。主后端负责用户授权、会话和持久化。

## 地址与兼容性

```http
POST /api/v1/rule-engine/validate
Content-Type: application/json
```

本地 Base URL 为 `http://localhost:8000`，远程调用替换为服务可达地址。
启动：`uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000`。
需预先配置数据库并发布活动规则。运行后访问 `/docs` 或 `/openapi.json`。
OpenAPI 仍只展示这一个接口；健康探针保留但隐藏，未新增查询、AI、管理路由。

旧的单税籍请求继续支持，响应原有字段保留并增加解释字段。
新请求支持 `tax_residencies` 数组；不可同时提交旧版顶层 TIN 字段和数组。
当前没有新增 API 认证，仅供内部服务接入。

## 请求体

| 字段 | 要求 |
| --- | --- |
| form_data | 必填，单税籍或多税籍表单，见下方 |
| policy | 必填，today 为业务日期 YYYY-MM-DD |
| indicia_issues | 可选，默认 []，最多 100 项上游问题 |
| include_guidance | 可选，默认 false；必须为 JSON 布尔值，true 请求 AI 补正，未配置或失败时固定提示降级 |

请求最大 1 MiB，未知字段拒绝。布尔值必须为 true/false；号码必须为字符串，保留前导零。
日期转换为 YYYY-MM-DD；不要直接传 PDF 中的 dd/mm/yyyy。
policy.today 由主后端明确提供；示例固定为 2026-11-04，不会自动跟随服务器日期。

### 个人版样例（兼容单税籍）

```json
{
  "form_data": {
    "holder_name": "CHAN DEMO",
    "holder_dob": "1990-05-20",
    "residence_address": "Flat 1, Demo Building, Demo Street, Hong Kong",
    "jurisdiction_code": "HK",
    "holder_type": "INDIVIDUAL",
    "tin_type": "HKID",
    "tin": "A123456(3)",
    "has_no_tin": false,
    "tin_reason_code": null,
    "tin_reason_explanation": null,
    "has_signature": true,
    "signing_date": "2026-11-04"
  },
  "policy": {
    "today": "2026-11-04"
  },
  "indicia_issues": []
}
```

### 实体版样例（不要求成立日期）

```json
{
  "form_data": {
    "holder_name": "DEMO CROSS BORDER LIMITED",
    "residence_address": "Room 101, Demo Commercial Building, Hong Kong",
    "jurisdiction_code": "HK",
    "holder_type": "ENTITY",
    "tin_type": "HK_BR",
    "tin": "12345678",
    "has_no_tin": false,
    "tin_reason_code": null,
    "tin_reason_explanation": null,
    "has_signature": true,
    "signing_date": "2026-11-04"
  },
  "policy": {
    "today": "2026-11-04"
  },
  "indicia_issues": []
}
```

### 多税籍样例（推荐新接入采用）

```json
{
  "form_data": {
    "holder_name": "CHAN DEMO",
    "holder_dob": "1990-05-20",
    "residence_address": "Flat 1, Demo Building, Demo Street, Hong Kong",
    "holder_type": "INDIVIDUAL",
    "has_signature": true,
    "signing_date": "2026-11-04",
    "tax_residencies": [
      {
        "jurisdiction_code": "HK",
        "tin_type": "HKID",
        "tin": "A123456(3)",
        "has_no_tin": false,
        "tin_reason_code": null,
        "tin_reason_explanation": null
      },
      {
        "jurisdiction_code": "GB",
        "tin_type": "GB_NINO",
        "tin": "AB123456C",
        "has_no_tin": false
      }
    ]
  },
  "policy": {
    "today": "2026-11-04"
  },
  "indicia_issues": [],
  "include_guidance": true
}
```

两个税籍仅为接口演示，不能根据地址或注册地推定某人实际拥有这些税收居民身份。
姓名、地址和号码均为虚构测试数据，不代表真实签发记录。

## 字段与官方表格映射

| 字段 | 类型与约束 | 表格来源／语义 |
| --- | --- | --- |
| holder_name | string，1–300 字符，纯空白阻断 | 个人 Part 1 姓名；实体 Part 1 法定名称 |
| holder_type | INDIVIDUAL / ENTITY；多税籍必填 | 主体类型；不是 Active/Passive NFE 分类 |
| holder_dob | string / null，最长 32 字符 | 个人出生日期必需；缺失返回业务阻断。实体不要求；旧实体请求仍可作为成立日期别名使用 |
| incorporation_date | string / null，最长 32 字符 | 可选实体成立日期。实体 PDF 无此字段，不得编造；提供时检查日期有效性。个人提供则业务阻断 |
| residence_address | string，1–2000 字符，纯空白阻断 | 个人现居住地址／实体营业地址，合并为字符串 |
| has_signature | boolean，必填 | 个人 Part 3／实体 Part 5 是否存在签名，由上游判断，不检查真伪 |
| signing_date | string / null，最长 32 字符 | 签署日期，必须有效且不晚于 policy.today |
| tax_residencies | 1–20 项数组，新版必填 | 个人 Part 2／实体 Part 4 的税收居民地区及 TIN；同一地区不能重复 |

旧版单税籍可以省略 holder_type，但正式 schema v2 规则要求明确主体类型，否则可能未覆盖转人工复核。
实体 holder_dob 与 incorporation_date 同时提供时必须一致；两者均可省略。
本接口不根据出生／成立日期自动判断税收居民身份，也不自定义年龄或实体存续年限。

数组每项字段如下；旧版单税籍将这些字段直接放在 form_data：

| 字段 | 类型与约束 |
| --- | --- |
| jurisdiction_code | 必填，两位大写地区代码；是税收居民地区，不是地址或注册地 |
| tin_type | string / null，最长 100 字符；香港个人 HKID、香港实体 HK_BR |
| tin | string / null；原文超过 256 字符产生业务阻断；清洗空白、括号、连字符并转大写 |
| has_no_tin | 必填 boolean；true 与非空 TIN 同时存在会阻断 |
| tin_reason_code | A / B / C / null；无 TIN 时必需，有 TIN 时不应提供 |
| tin_reason_explanation | string / null，最长 4000 字符；Reason B 去首尾空白后至少 5 字符 |

无 TIN 时：has_no_tin=true、tin=null，并填写 A/B/C；B 还需解释实际原因。
仅检查声明完整性，豁免适用性仍需人工复核，不会仅凭声明自动放行。
支持的地区、主体和标识类型见 [规则覆盖说明](../../rules/GLOBAL_COVERAGE.md)。

policy 还可包含 earliest_signing_date（可选最早签署日期，不得晚于 today）、strict_coverage（默认 true）。
strict_coverage=false 仅影响旧 schema v1 的长度兜底，不会关闭 schema v2 未覆盖复核。
indicia_issues 每项必须含 code、severity（BLOCKER/WARNING）、message、confidence（0–1），field 可省略/null。
上游问题参与同一严重级别汇总，不会因来源不同而被忽略。

## 调用示例

在仓库根目录执行：

```bash
curl -X POST http://localhost:8000/api/v1/rule-engine/validate \
  -H 'Content-Type: application/json' \
  --data-binary @assets/crs-templates/crs-multi-residence-request.json
```

个人／实体单税籍分别替换文件名为 crs-individual-request.json、crs-entity-request.json。

```python
import httpx

async def validate_form(body: dict) -> dict:
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30) as client:
        response = await client.post("/api/v1/rule-engine/validate", json=body)
        response.raise_for_status()
        return response.json()
```

## 响应与前端展示

| 字段 | 含义 |
| --- | --- |
| verdict | AUTO_PASS / NEED_USER_FIX / MANUAL_TRIAGE |
| issues | 引擎问题在前，上游问题在后；每项 code、severity、field、message、confidence |
| rule_version_id / rule_revision | 全部税籍和 AI 工具引用固定使用的本次规则版本 |
| checks | 旧版单税籍 TIN 检查，兼容保留；多税籍返回 null，请读取 residence_results |
| execution | 引擎构建指纹、规范化输入指纹和策略，不包含 AI 文案指纹 |
| residence_results | 每项 index、jurisdiction_code、checks、issue_indexes；index 对应税籍数组下标 |
| check_items | 姓名、地址、个人／实体日期、签名、签署日期和每项税籍声明的检查状态及问题下标 |
| issue_origins | 每项 issue_index、source（RULE_ENGINE/UPSTREAM）、evidence_ref（issue:N） |
| review_scope | 已执行范围、未评估项目及说明，前端应展示，避免把 AUTO_PASS 当成整表合规认证 |
| guidance | 可选 AI 的状态、通用错误 category/retryable、补正动作、引用、模型及提示词／输出指纹，见下一节 |

TIN checks 包含 status（PASSED/FAILED/NOT_COVERED/NOT_APPLICABLE）、verification_level
（FORMAT_ONLY/CHECKSUM/NONE）、rule_id、source_url、algorithm_source_url、checks_performed、checks_not_performed、reason_code。
check_items.status 为 PASSED/FAILED/REVIEW_REQUIRED/NOT_APPLICABLE。
实体未提供可选日期时相关检查显示 NOT_APPLICABLE。
多税籍问题路径示例：`tax_residencies.1.tin`；公共缺签等问题只返回一次。
issue_indexes 均引用顶层 issues 数组，避免前端依赖问题消息字符串做判断。

| 裁决 | 条件 | 建议展示 |
| --- | --- | --- |
| NEED_USER_FIX | 任意 BLOCKER | 需要补正，展示对应字段问题 |
| MANUAL_TRIAGE | 无 BLOCKER，但存在 WARNING | 待人工复核 |
| AUTO_PASS | 当前检查无问题 | 当前检查通过，同时展示审核范围 |

两份单税籍样例和多税籍样例在当前 global v4 下无上游问题时预期 AUTO_PASS；
香港和本例英国 NINO 都仅 FORMAT_ONLY，不代表号码签发、归属或实际税收居民身份已经核实。
正常业务裁决均为 HTTP 200，必须读取 verdict。

## AI 补正结果

include_guidance=false（默认）不调用模型，guidance.status=NOT_REQUESTED。
true 时服务器按配置调用模型；AI 不修改裁决、严重级别、原始字段和规则。

以下为单个错误 TIN 的 guidance 结构示意，不是前述通过样例的完整响应：

```json
{
  "status": "GENERATED",
  "reason_code": null,
  "error": null,
  "summary": "请核对原始证件上的号码。",
  "actions": [
    {
      "issue_index": 0,
      "field": "tin",
      "instruction": "请确认税收居民地区与标识类型，再依据原始资料补正号码。",
      "evidence_refs": ["issue:0", "rule:0"]
    }
  ],
  "model": "<配置的模型标识>",
  "prompt_version": "remediation-v2",
  "prompt_fingerprint": "<提示词指纹>",
  "duration_ms": 1000,
  "metrics": {
    "attempts": 2,
    "retries": 0,
    "provider_duration_ms": 800,
    "queue_duration_ms": 0,
    "prompt_tokens": 200,
    "completion_tokens": 60,
    "total_tokens": 260,
    "usage_complete": true
  },
  "output_fingerprint": "<补正 summary/actions 的规范化哈希>"
}
```

issue:N 引用顶层 issues[N]；rule:N 引用 residence_results[N].checks 及其官方来源。
无匹配规则或未读取该规则工具时不允许引用 rule:N。
GENERATED 仍仅是辅助文案，需按用户真实资料补正，不能作为税务适用性结论。

未启用／配置模型、超时、服务错误、无效引用或输出不完整时，status=FALLBACK，
返回固定补正提示；reason_code 区分 AI_NOT_CONFIGURED、AI_TIMEOUT、鉴权／权限／限流／端点错误和输出异常。
百炼接入与完整错误码见 [百炼配置说明](../../backend/agents/BAILIAN.md)。
guidance.error 在未请求或成功时为 null；降级时含 category 和 retryable。
category 包含 configuration、authentication、permission、quota、rate_limit、timeout、connection、
invalid_request、invalid_response、service_unavailable、internal。
限流、超时、连接和服务不可用标记 retryable=true；鉴权、额度、参数或输出错误标记 false。
retryable 是恢复建议；服务端仅对明确限流及 500/502/503，在总预算内共享最多 1 次重试。
Retry-After 超出剩余预算时直接降级；设置 RULE_AI_MAX_RETRIES=0 关闭。供应商状态和错误码仅用于内部诊断。
旧 AI_MODEL_OR_ENDPOINT_NOT_FOUND 统一为 AI_REQUEST_REJECTED；旧 AI_OUTPUT_OR_SERVICE_ERROR 拆分为明确分类。
不要因 AI 降级而将已完成的规则结果当作失败或通过。
主后端保存 guidance 的实际输出及元数据，不能假设重新调用模型逐字重现。

guidance.metrics 返回本次请求的 attempts、retries、provider_duration_ms、queue_duration_ms、
prompt_tokens、completion_tokens、total_tokens、usage_complete。
只有 usage_complete=true 才表示全部尝试都报告了完整且一致的用量；否则 token 只反映已知部分，不是实际账单。
guidance.duration_ms 是含并发排队和重试退避的总 AI 耗时；总预算仍默认 8 秒，不因重试延长。
读超时、发送后断连、408/504、永久错误或无效输出不自动重发；错误提示中的 retryable 与自动重试范围不同。


### 服务端启用 AI

在 `.env` 中配置（密钥不要提交）：

```dotenv
RULE_AI_ENABLED=true
RULE_AI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
RULE_AI_API_KEY=<组委会提供的密钥>
RULE_AI_MODEL=qwen-plus
RULE_AI_TIMEOUT_SECONDS=8
RULE_AI_MAX_CONCURRENCY=2
RULE_AI_MAX_RETRIES=1
```

如组委会提供其他兼容网关，替换 base URL；代码自动追加 `/chat/completions`。
修改配置后重启服务。配置参考仓库 [.env.example](../../.env.example)。
服务端默认允许 AI，但默认请求不调用模型；需传 include_guidance=true 并填入有效 Key。
默认模型 qwen-plus 可通过 RULE_AI_MODEL 覆盖，部署时可指定具体版本。
也支持标准 DASHSCOPE_API_KEY；非空 RULE_AI_API_KEY 优先，空占位不会遮蔽标准 Key。
当前官方原文工具明确返回“未安装核实正文”，只可使用已有规则元数据及来源，不会生成官方原文引文。

## 错误

```json
{
  "code": "VALIDATION_ERROR",
  "message": "Invalid request JSON or field values",
  "details": [
    {"field": "form_data.has_signature", "code": "bool_type", "message": "Expected a JSON boolean"}
  ]
}
```

422 返回最多 20 条安全字段错误；不回显原始输入、异常上下文或任意未知字段名。
未知字段路径显示 <unknown>。日期内容错误、缺签和缺少个人出生日期等业务问题返回 200 + issues。

| HTTP | code | 说明 |
| --- | --- | --- |
| 413 | REQUEST_TOO_LARGE | 请求超过 1 MiB |
| 422 | VALIDATION_ERROR | JSON、字段类型、未知字段、税籍数组、策略组合不合法 |
| 503 | NO_ACTIVE_RULES | 未发布活动规则 |
| 503 | RULE_ENGINE_UNAVAILABLE | 数据库或规则不可用 |
| 500 | INTERNAL_ERROR | 未预期系统错误 |

## 当前范围与结果保存

- 支持最多 20 个不同税收居民地区，一次请求使用一份固定快照，BLOCKER 优先于 WARNING 汇总。
- 不核实是否遗漏其他税收居民地区，也不核实真实身份、TIN 签发／归属和签名真伪。
- 实体分类、控权人、授权签署人等完整表格信息仍未纳入契约，不应额外提交。
- 每次调用读取当时的活动版本；重试可能因规则更新得到不同结果。
- HTTP 不写审核记录；主后端保存请求、完整响应和原始文件引用。内部历史归档／重放接口不适用于多税籍 HTTP 文档结果。
- 本轮包含模拟模型 HTTP 工具调用测试；真实组委会模型需配置后联调，不能将 Mock 测试等同于真实模型可用性验证。
