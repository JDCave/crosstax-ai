# 百炼补正 Agent 接入

规则校验仍通过 `POST /api/v1/rule-engine/validate` 完成。
百炼仅为已发现的问题生成补正建议，不参与号码算法、税籍认定或最终裁决。

## 填入 Key 后使用

项目根目录 `.env` 已预留配置，默认模型为 `qwen-plus`：

```dotenv
RULE_AI_ENABLED=true
RULE_AI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
RULE_AI_API_KEY=
RULE_AI_MODEL=qwen-plus
RULE_AI_TIMEOUT_SECONDS=8
RULE_AI_MAX_CONCURRENCY=2
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
总预算仍为默认 8 秒、最多 4 轮和 12 次工具调用；不自动重试，以免放大耗时和调用费用。
当前没有核实的官方正文片段，原文工具返回 unavailable；模型只能引用已有规则和问题证据。

## 降级状态

业务 HTTP 状态仍为 200，检查 guidance.status 和 reason_code：

| reason_code | 排查方向 |
| --- | --- |
| AI_NOT_CONFIGURED | 未启用、未填入 Key |
| AI_AUTHENTICATION_FAILED | 百炼返回 401，检查 Key 与地域 |
| AI_PERMISSION_DENIED | 百炼返回 403，检查业务空间／模型权限 |
| AI_MODEL_OR_ENDPOINT_NOT_FOUND | 百炼返回 404，检查模型名与 base URL |
| AI_RATE_LIMITED | 百炼返回 429，检查限流与额度 |
| AI_REQUEST_REJECTED | 百炼返回 400，检查模型是否支持当前工具与非思考参数 |
| AI_PROVIDER_UNAVAILABLE | 其他供应商错误，稍后重试或检查控制台 |
| AI_TIMEOUT | 超过配置预算，包含并发排队时间 |
| AI_OUTPUT_OR_SERVICE_ERROR | 输出不完整、引用不可信、协议异常或工具预算耗尽 |

不回传百炼原始错误正文，避免带出输入、密钥或内部信息。
主后端应保存实际指导文案、模型名、prompt_version、prompt_fingerprint 和 output_fingerprint。
当前提示词版本为 remediation-v2；规则执行指纹与 AI 文案指纹分别记录。

## 验证范围

自动测试使用 MockTransport 校验真实请求结构、工具／JSON 两阶段、Key 优先级、地域入口覆盖、
错误分类、超时降级和个人资料不外发，不包含真实付费模型调用。
填入有效 Key 后，需按上述错误号码示例完成真实模型联调；尚未实测真实供应商的延迟和输出质量。
