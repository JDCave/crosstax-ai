# 竞赛展示能力与快速初始化设计

本轮由用户重新授权，只增强规则引擎的解释、补正对比、模拟升级演示及初始化，不扩展主会话、前端脚手架或生产监控。

## 1. 解释卡片

ValidationResponse 增加 explanation_cards；每个已有 issue 对应一张卡片，包含标题、严重度、字段、原因、补正动作、动作来源、证据引用和实际 TIN 来源。
卡片是展示派生数据，不修改 issue、检查、置信度或 verdict。
补正 Agent 生成且通过既有验证的对应动作优先；未请求或降级时使用确定性展示模板，不再调用 AI。
表单政策、TIN 规则和上游问题明确区分；不存在官方出处时不编造 URL 或引用。
旧结果缺少卡片时从保存的结果派生展示，旧 READY PDF 不重新生成；新报告模板升级 v2，加入解释和补正动作。

## 2. 补正前后对比

GET tasks/{task_id}?compare_to=旧任务UUID，仍使用现有查询路径；默认不比较。
两个任务必须同一 session_id、均成功且未过期，比较不修改或重跑任何任务。
返回 verdict 前后、修复/新增/保留的问题、变化字段路径和上下文差异。
不返回字段原始值，避免比较摘要泄露姓名/TIN；列表重复问题按多重集合处理。
规则内容版本/revision、业务日期政策、表单策略、引擎构建不一致时标记 DIFFERENT_CONTEXT，不能把结论变化全部归因于用户补正。
对比结果仅附加在本次 GET 的 comparison 字段，不修改已加密结果或已生成 PDF。
变化字段输出最多 200 项，另给总数和截断标记；问题差异最多各 200 项，明确截断。

## 3. 规则升级演示

GET /api/v1/rule-engine/demo/upgrade-impact，仅 RULE_DEMO_ENABLED=true 时启用并展示于 Swagger，默认关闭。
复用现有 v1/v2 演示包、Case A–E、impact 分析器，离线输出前后结论、风险和版本指纹。
响应 simulation=true，明确“合成演示用例和模拟补丁，不代表最新官方法规”。不加载当前 DB 规则、不写发布记录、不切换活动版本、不调用 AI。
前端据现有差异结果展示 Case E 即可，不增加发布 UI。

## 4. 初始化 API

POST /api/v1/rule-engine/setup/initialize，固定空请求体 {}，不接受数据库 URL、SQL、规则正文或文件路径。
默认关闭，不出现在业务 Swagger；RULE_SETUP_ENABLED=true 且 RULE_SETUP_TOKEN 至少 24 字符时可用，调用需 X-Setup-Token。
只初始化已经可连接的数据库，不负责创建 RDS 实例、PG 数据库或账号。
通过 SQLAlchemy DDL 建立 crosstax schema 和历史六表基线，再复用已有 Alembic 迁移到 head；不执行手写 PG SQL，不创建 User 或主后端业务表。
支持空规则 schema、完整六表基线以及正常由项目迁移跟踪的数据库；对不一致的手工结构拒绝，不盲目 stamp、DROP 或覆盖。
已有表先检查列/类型/主键等兼容性，迁移后再核对结构。
迁移和种子数据分阶段提交；中途失败可能保留已完成阶段，重复调用安全继续，不声称整次操作完全原子。
初始化只补缺：协调状态行、OECD 来源 manifest 三项、仓库 global v4 规则。规则须通过现有回归门禁；已拒绝版本不改为批准。
仅在尚无活动规则时激活默认已批准版本，已有活动版本和发布历史保持不变。已有来源不改名、不重新启用。
不抓网页、不导入虚构文档、不创建税号/审核任务/PDF、不生成密钥。
使用现有单机文件锁防同机多进程重复初始化；竞赛单实例部署仅开放一个初始化实例，不提供跨主机分布式锁。
完成后返回迁移版本、表数量、来源新增数、默认版本及实际活动版本、Worker/密钥配置提示；不返回口令、URL 凭据或业务数据。
初始化完成后关闭 RULE_SETUP_ENABLED。该口令仅保护建表入口，不扩展用户鉴权体系。

## 5. 全流程与验收

初始化 → 配置任务密钥并启动现有双循环 Worker → 提交缺签样例 → 查询卡片 → 补正后用同 session_id/新幂等键提交 → 带 compare_to 查询对比 → 等待报告并下载；模拟升级独立演示不影响正式任务。
现有三条业务接口默认仍保持三条；初始化入口始终不进业务 Swagger，模拟演示只有开启后额外展示。
无新业务表或列，卡片保存在现有加密结果中，对比仅临时计算。同步完整 SQL、数据库设计和本地 PG，最后更新进度表。
验证涵盖卡片不改裁决、AI 证据选择、重复问题对比、上下文变化、跨会话/过期/未完成错误、初始化默认禁用/口令/重复调用/保护活动版本/空库迁移、PG 与 Worker 到 PDF 链路。

## 实现落点与交付

- services/presentation.py 和 schemas/presentation.py：确定性卡片及证据，services/rule_api.py 保存进现有加密结果。
- services/task_comparison.py：问题多重集合与输入路径差异；GET task 通过 compare_to 触发，不新增业务查询路由。
- services/competition.py / api/routes/competition.py：显式模拟升级与默认关闭的口令初始化。
- infrastructure/schema_setup.py：ORM 六表基线与 Alembic 已有连接迁移；不自动 stamp；隔离 schema 支持真实 PG 测试。
- Dockerfile 与 dockerignore：补齐来源 manifest 供初始化，保留原规则／Case／字体打包。

本轮不新增数据表或列，完整 SQL 已重新生成并检查一致。新展示信息进入现有结果密文，对比不落库。
本地初始化服务已复核并同步，活动版本/revision=3 保留，仅补齐缺失的队列协调行。
316 项测试全部通过，包含 PG 初始化、队友表保护及初始化后的 PDF 链路；Ruff/Mypy 通过。
接口使用与开关示例见 [竞赛能力文档](../api/COMPETITION_API.md)。未启用本地常驻初始化入口或启动云端服务。
