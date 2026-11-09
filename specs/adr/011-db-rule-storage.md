# ADR-011: 数据库存储规则（取代 ADR-003）

## 状态
已采纳 (2026-11-09)。取代 ADR-003（JSON 文件存储规则），并推翻 2026-11-05 变更单第 25 项「维持 ADR-003」的裁定。

## 背景
ADR-003 于 2026-10-22 选择 JSON 文件载体，2026-11-05 曾以「推翻已评估方案需新信息」为由裁定维持。此后规则引擎实际按数据库版本存储建成并持续演进（注册→批准→激活/回滚、发布审计、影响分析、受控后台更新），文档与实现的偏离被登记为待团队拍板事项。2026-11-09 团队裁定：规则载体为数据库。

## 决策
规则的唯一权威载体为 ADR-008 应用数据库（开发 SQLite / 生产 PG，`crosstax` schema）：
- 规则内容以 JSON 文档存于 `rule_versions.rules`（JSON 列），`version_id` = 规范化 JSON 内容的 SHA-256（ADR-003 的哈希绑定保留）
- 版本经 `CANDIDATE → APPROVED → 激活` 流转，激活/回滚写入 append-only `rule_publications`，`revision` 单调递增
- 运行时 `RuleLoader.refresh()` 从数据库读取活动版本，校验哈希与结构后原子替换内存不可变快照（热重载语义保留，无需重启）

## 否决方案
- **JSON 文件载体（ADR-003）**：热重载虽简单，但无版本审批流与发布审计，多实例一致性依赖文件同步；引擎已按 DB 落地并有测试覆盖，回退成本高于收益

## 理由
- 推翻 11-05 裁定所需的新信息已成立：DB 版本存储不再是「零实现的契约先行文档」，而是已实现并配套审批、审计、影响分析与自动化测试的现行系统
- 审计溯源要求规则版本持久化、可查询（`RuleAuditRecord` 绑定 `version_id`），文件方案无法满足
- ADR-003 的两个核心目标——热重载、内容哈希版本绑定——在 DB 方案下同等成立

## 后果
- `rules/*.json` 降级为注册输入与种子工件（CLI `register`、初始化服务、竞赛演示、测试夹具），不再是运行时载体
- 规则引擎依赖应用数据库：库不可用或无活动规则 → 503（`RULE_ENGINE_UNAVAILABLE` / `NO_ACTIVE_RULES`）
- `rule_revision` 语义为 `rule_publications.revision`（发布级），不再是 v1_base/v2_patch 的补丁级
- 不新增数据库依赖，连接池沿用 ADR-010 限制
- ADR-003 标记 superseded；`AGENTS.md` Guardrail、`specs/data-spec.md` §3、`specs/prd.md` F3、`design/architecture.md`、README 相关表述以本 ADR 为准

## 实现状态
已实现：`backend/engine/rule_loader.py`、`backend/engine/publication.py`、`backend/repositories/rules.py`、`backend/models/rule_*.py`；迁移 `20261103_rule_history`、`20261108_rule_tasks_durable_encrypted_rule_validation_tasks`。运行契约见 `assets/crs-templates/API_INTEGRATION.md`，详细设计见 `backend/engine/RULE_ENGINE.md`。