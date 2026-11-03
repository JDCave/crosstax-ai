# 百炼补正 Agent 接入

规则校验仍通过 `POST /api/v1/rule-engine/validate` 完成。
百炼仅为已发现的问题生成补正建议，不参与号码算法、税籍认定或最终裁决。

## 填入 Key 后使用

项目根目录 `.env` 已预留配置，默认模型为 `qwen-plus`，允许用 `RULE_AI_MODEL` 指定其他可用模型或具体版本：

```dotenv
RULE_AI_ENABLED=true
RULE_AI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
RULE_AI_API_KEY=
RULE_AI_MODEL=qwen-plus
RULE_AI_TIMEOUT_SECONDS=8
RULE_AI_MAX_CONCURRENCY=2
RULE_AI_MAX_RETRIES=1
```

将你的 Key 填入 `RULE_AI_API_KEY`，重启后端即可。
也支持标准环境变量 `DASHSCOPE_API_KEY`：非空 RULE_AI_API_KEY 优先，否则使用 DASHSCOPE_API_KEY；空占位不会遮蔽标准 Key。
未填 Key 时返回固定补正提示，不发起百炼调用。
服务端允许 AI，调用方仍需明确传 `include_guidance: true`；默认请求不会调用模型。
如原有本地配置已设置 RULE_AI_ENABLED=false，需改为 true。
`.env` 不进入 Git，团队可复制 [.env.example](../../.env.example) 建立自己的配置。

启动服务：

```bash
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

将表单请求 JSON 顶层加入 `"include_guidance": true`；完整多税籍样例已包含此字段：

```bash
curl -X POST http://localhost:8000/api/v1/rule-engine/validate \
  -H 'Content-Type: application/json' \
  --data-binary @assets/crs-templates/crs-multi-residence-request.json
```

当前通过样例一般没有待补正问题。验证补正演示时，可以把示例中一个 tin 改成 `WRONG`：
预期 verdict=NEED_USER_FIX，模型可用且输出有效时 guidance.status=GENERATED。
即使模型失败，verdict 和 issues 仍按规则返回。

## 模型与地域

默认使用百炼 Qwen 模型 API 的 Chat Completions 兼容接口；不需要安装 OpenAI 或 DashScope SDK，复用已有 httpx。
服务端发送 `enable_thinking=false` 和 `stream=false`，适配当前同步、有限时的补正流程。
模型允许通过 RULE_AI_MODEL 修改，需具备 Function Calling 和非思考模式 JSON 输出能力。

默认 URL 是北京 DashScope 兼容入口。如果组委会给的是业务空间专属入口，
将 RULE_AI_BASE_URL 替换成控制台提供的完整 base URL，例如：

```text
https://实际业务空间ID.cn-beijing.maas.aliyuncs.com/compatible-mode/v1
https://实际业务空间ID.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1
```

不要原样保留占位符；不要追加 `/chat/completions`，程序自动追加。
URL 必须为 HTTPS，不得包含用户名、密码、查询参数或片段。
API Key、地域和模型权限需要对应；不同地域 Key 不可混用。
[官方地域与接入信息](https://help.aliyun.com/zh/model-studio/regions)。

## 工具与 JSON 输出分阶段

1. 证据阶段：请求带 tools、tool_choice=auto、parallel_tool_calls=true，不同时设置 response_format。
2. 应用执行模型选定的白名单只读工具，写回 tool_call_id 对应的工具消息。
3. 收集对应问题和匹配规则后，最终请求不再带 tools，使用 response_format={"type":"json_object"}。
4. 返回的 JSON 继续经过 Pydantic、引用、字段和动作完整性校验，不能仅凭 JSON 格式有效就接受。

该实现遵循[百炼 Function Calling](https://help.aliyun.com/zh/model-studio/qwen-function-calling)多轮协议，
非思考模式与 JSON 参数依据[官方结构化输出说明](https://help.aliyun.com/zh/model-studio/qwen-structured-output)。
总预算仍为默认 8 秒、最多 4 轮和 12 次工具调用。
HTTP 429（可恢复限流）、500/502/503 可在预算内重试；默认整个 Agent 合计最多额外 1 次，不是每轮各重试一次。
RULE_AI_MAX_RETRIES 可设为 0 关闭、最多 2；默认最多 5 次 HTTP 尝试（4 轮加 1 次重试）。
优先遵循 Retry-After 秒数或 HTTP 日期；未提供时使用带抖动的指数退避。
等待时间超出剩余总预算时直接返回原失败，不缩短服务端要求的等待。
鉴权、权限、额度、参数、输出错误，以及读超时／连接异常／HTTP 408/504 不自动重发，避免执行状态不明时重复调用。
不自动切换模型。排队、网络、工具轮次和重试等待均计入原有总预算。
响应在传输接收时累计检查 256 KiB 上限，超过后立即停止读取并关闭连接。gzip 等压缩内容按解码后的字节检查。
当前没有核实的官方正文片段，原文工具返回 unavailable；模型只能引用已有规则和问题证据。

## 通用错误分类与降级状态

业务 HTTP 状态仍为 200，检查 guidance.status 和 reason_code：

guidance.error 在成功或未请求时为 null；降级时包含供应商无关的 category 和 retryable。
例如鉴权失败返回：

```json
{
  "status": "FALLBACK",
  "reason_code": "AI_AUTHENTICATION_FAILED",
  "error": {"category": "authentication", "retryable": false}
}
```

该片段省略固定补正 actions 等其他字段，完整结构见接口文档。

| category | reason_code | retryable | 排查方向 |
| --- | --- | --- | --- |
| configuration | AI_NOT_CONFIGURED | false | 启用配置、填入 Key |
| authentication | AI_AUTHENTICATION_FAILED | false | Key 与地域是否匹配 |
| permission | AI_PERMISSION_DENIED | false | 业务空间或模型权限 |
| quota | AI_QUOTA_EXCEEDED | false | 欠费、预算或额度，需先处理控制台配置 |
| rate_limit | AI_RATE_LIMITED | true | 降低并发／请求与 token 速率 |
| timeout | AI_TIMEOUT | true | 总预算、模型或网络耗时；包含 408/504 |
| connection | AI_CONNECTION_ERROR | true | DNS、连接或传输错误 |
| invalid_request | AI_REQUEST_REJECTED | false | 请求参数、模型名或端点路径；包含 400/404/413/422 |
| invalid_response | AI_INVALID_RESPONSE | false | 非法 JSON、引用错误、动作不完整或工具预算耗尽 |
| service_unavailable | AI_PROVIDER_UNAVAILABLE | true | 供应商 5xx 或资源拥塞 |
| internal | AI_INTERNAL_ERROR | false | 应用内部异常，联系维护者 |

retryable 是一般恢复建议；服务端仅按上述更严格的有限重试策略处理，不保证重试成功。
根据百炼 HTTP 状态和已知 error.code/error.type 白名单分类，未识别代码回退到 HTTP 状态。
Arrearage、BudgetLimitExceeded、insufficient_quota 等归入 quota，不与普通 429 限流混为一类。
Throttling.AllocationQuota 按 token 速率限制处理；同类供应商代码也可能因套餐限制出现，仍需按控制台确认实际原因。
具体状态码和白名单内供应商代码仅保留于内部诊断，不向调用方暴露原始供应商错误正文。
映射依据 [百炼官方错误码](https://help.aliyun.com/en/model-studio/error-code)。
旧的 AI_MODEL_OR_ENDPOINT_NOT_FOUND 统一为 AI_REQUEST_REJECTED，AI_OUTPUT_OR_SERVICE_ERROR 拆分为连接、输出与内部错误。

不回传百炼原始错误正文，避免带出输入、密钥或内部信息。
主后端应保存实际指导文案、模型名、prompt_version、prompt_fingerprint 和 output_fingerprint。
生产部署若需要稳定回放，应显式指定可用的具体模型版本；不自动切换或降级到其他模型。
当前提示词版本为 remediation-v2；规则执行指纹与 AI 文案指纹分别记录。

## 验证范围

自动测试使用 MockTransport 校验真实请求结构、工具／JSON 两阶段、Key 优先级、地域入口覆盖、
错误分类、超时降级和个人资料不外发，不包含真实付费模型调用。
填入有效 Key 后，需按上述错误号码示例完成真实模型联调；尚未实测真实供应商的延迟和输出质量。


## 耗时、次数和用量

返回的 guidance.metrics 为当前请求独享，不跨并发请求累计：

| 字段 | 含义 |
| --- | --- |
| attempts | 发起的 HTTP 尝试数，含失败与重试 |
| retries | 已启动的额外重试数，跨全部模型轮次共享上限 |
| provider_duration_ms | HTTP 请求与读取响应所耗时间之和，不含退避等待 |
| queue_duration_ms | 等待 Agent 并发名额的时间，超时排队也记录 |
| prompt_tokens / completion_tokens / total_tokens | 百炼响应中已报告的 token 数累计 |
| usage_complete | 每次尝试是否都提供了完整、有效且一致的 usage |

guidance.duration_ms 仍是整体 AI 耗时，包含排队、退避和模型调用。
缺少 usage、失败、取消、超时或统计字段非法时 usage_complete=false，token 为已知部分，不能当作实际计费总量。
未请求 AI 或未配置 Key 时 attempts=0，不会产生模型调用。
这些统计不是账单估算，也不包含规则数据库查询耗时；实际费用以百炼控制台为准。
本轮测试包含限流恢复、共享重试上限、Retry-After、永久错误不重试、总时限取消、并发统计隔离、
部分 usage 和超大／压缩响应处理。真实付费调用仍待填 Key 后验证。
