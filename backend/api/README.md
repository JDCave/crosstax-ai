# API 接口文档

- [规则引擎 HTTP API](RULE_ENGINE_API.md)：请求字段、响应、错误码、幂等及调用示例。
- [OpenAPI JSON 快照](openapi.json)：由当前 FastAPI 应用生成，可导入支持 OpenAPI 的接口工具。
- 服务运行后 `/docs` 提供交互式文档，`/openapi.json` 提供实时契约。

现有健康接口为 `GET /health` 与 `GET /ready`；规则引擎接口统一位于 `/api/v1/rule-engine`。
OpenAPI 快照不包含本地数据库凭据或服务器地址。接口变更后需重新从 `create_app().openapi()` 导出。
