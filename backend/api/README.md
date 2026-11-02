# API 接口文档

队友只调用 **POST /api/v1/rule-engine/validate**：传入数据，同步返回校验结果。
无需 session_id、结果查询、规则查询或重放 API，接口不强制保存审核数据。

- [接口字段、响应与调用示例](RULE_ENGINE_API.md)
- [OpenAPI JSON 快照](openapi.json)
- 运行服务后访问 `/docs` 和 `/openapi.json`

现有健康接口 `/health`、`/ready` 保留。规则维护和历史重放仍是内部 Python/CLI 能力。
