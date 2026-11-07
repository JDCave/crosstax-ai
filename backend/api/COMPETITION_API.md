# 竞赛能力接口

详细设计见 [竞赛功能设计](../engine/COMPETITION_FEATURES.md)。

- 解释卡片：原任务 result.explanation_cards，沿用既有业务接口与 verdict。
- 补正对比：GET /api/v1/rule-engine/tasks/{新任务UUID}?compare_to={旧任务UUID}，结果附加 comparison；同一主会话且两个任务均成功。
- 模拟升级：GET /api/v1/rule-engine/demo/upgrade-impact，需 RULE_DEMO_ENABLED=true；仅读演示配置，不更新真实规则。
- 初始化：POST /api/v1/rule-engine/setup/initialize，body {}，X-Setup-Token 匹配 RULE_SETUP_TOKEN；仅 RULE_SETUP_ENABLED=true 开放，始终从业务 Swagger 隐藏。

初始化使用现有 DATABASE_URL；数据库本身必须已存在，账号需要 schema/建表/迁移权限。
它会创建/迁移规则表、补齐内置来源与通过回归的 global v4，仅无活动版本时激活；不会清空数据或生成审核任务。
初始化后仍需提供共享 RULE_TASK_ENCRYPTION_KEYS 并启动 `uv run python -m backend.workers.rule_tasks`。
原 PDF 下载路径和 REPORT_GENERATING 重试约定不变。

预期错误：未开启 404；初始化口令不匹配 403；初始化忙碌或数据库结构冲突 409；数据库不可连接/初始化配置无效 503。
对比：同一任务/跨会话 422或409，未完成409，过期410，不存在404。对比不返回字段原始值。

前端：先显示解释卡片；补正提交必须换幂等键，保留相同 session_id；拿新 task_id 对比旧 task_id。
若 comparison 标记不同执行上下文，应提示规则/日期/构建不同，不能宣称完全是用户修复造成。
模拟升级页面必须保留 simulation 标记，不把演示补丁宣传为最新官方法规。
