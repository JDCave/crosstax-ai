# API 接口文档

当前共三条接口，按调用方区分：

1. 上游后端：`POST /api/v1/rule-engine/tasks`：接收表单并持久化，返回 task_id。
2. 上游后端：`GET /api/v1/rule-engine/tasks/{task_id}`：查询状态，完成时返回完整校验结果与 report_url。
3. 前端：`GET /api/v1/rule-engine/tasks/{task_id}/report`：仅下载 SUCCEEDED 任务的 PDF。

- [前端 PDF 下载、错误与阿里云对接](PDF_REPORT_API.md)
- [异步接入、错误、重试及 Worker 启动](RULE_TASKS_API.md)
- [结构化表单字段与主流程职责](STRUCTURED_CRS_API.md)
- [旧同步格式兼容说明](RULE_ENGINE_API.md)
- [OpenAPI 快照](openapi.json)，运行服务后访问 `/docs`、`/openapi.json`

Swagger 只展示上述三条接口。旧同步 `/validate` 和健康探针保留且隐藏。
规则维护、资料同步和历史重放仍为内部 Python/CLI 能力，不增加管理 API。

任务输入、固定规则/表单策略快照及结果加密保存，默认保留 24 小时。
主后端继续负责用户鉴权、AuditSession、抽取、跨源汇总和最终会话状态，不需要直接轮询数据库。

[百炼 Agent 配置](../agents/BAILIAN.md)：默认 qwen-plus，设置 Key 后传 include_guidance=true。
[后台规则更新](../engine/RULE_UPDATES.md)与规则验证 Worker 是两个独立职责，不能互相替代。
