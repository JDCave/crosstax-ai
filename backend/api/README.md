# API 接口文档

队友只调用 **POST /api/v1/rule-engine/validate**：传入数据，同步返回校验结果。
无需 session_id、结果查询、规则查询或重放 API，接口不强制保存审核数据。

- [接口字段、响应与调用示例](RULE_ENGINE_API.md)
- [OpenAPI JSON 快照](openapi.json)
- 运行服务后访问 `/docs` 和 `/openapi.json`

接口文档只展示一个校验接口；`/health`、`/ready` 仅作为内部探针保留，不出现在 OpenAPI 中。重复的 `/redoc` 文档入口和未使用的 OAuth2 回调入口已关闭。规则维护和历史重放仍是内部 Python/CLI 能力。

支持兼容单税籍请求与 1–20 项多税籍请求；`include_guidance=true` 可选请求补正 Agent，失败自动降级。
[队友接入指南与表格样例](../../assets/crs-templates/API_INTEGRATION.md)包含实体日期处理、逐项结果、字段映射和 AI 配置说明。

[百炼 Agent 配置与联调](../agents/BAILIAN.md)：默认 qwen-plus，填入 Key 并重启后，在请求中传 include_guidance=true。

[后台规则更新与每日调度](../engine/RULE_UPDATES.md)为内部 CLI 能力，不增加队友需要调用的 API。
