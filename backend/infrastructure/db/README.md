# Validation Engine 数据层设计

本目录保存规则引擎的数据层设计和 PostgreSQL 建表评审稿。
`validation_engine.sql` 尚未执行；正式部署应通过 SQLAlchemy 模型和 Alembic 迁移完成。
复用现有 `backend/infrastructure/database.py` 的数据库连接与会话，不创建第二套连接池。
连接池应遵守 ADR-010：`pool_size=3`、`max_overflow=0`。

## 范围与流程

官方资料定时采集 → 原始文档入库 → AI 提取候选规则 → 校验与测试 → 批准版本 → 激活版本 → 引擎加载内存快照。

数据库保存规则和来源，内存快照执行校验。每次审核开始时绑定一个版本，执行过程中不切换版本。
审核会话、输入、结果由主后端保存；引擎返回 `rule_version_id`，与现有 AuditSession 契约对接。

## 数据表

| 表 | 职责 |
| --- | --- |
| rule_sources | 官方来源 URL、法域、启用状态、HTTP 缓存信息、最近检查时间 |
| rule_sync_runs | 定时/手动同步的状态、起止时间、摘要和错误 |
| rule_documents | 原始字节、提取正文、内容哈希、来源与首次产生该文档的同步任务 |
| rule_versions | 完整规则 JSON、内容版本、候选/批准/拒绝状态、验证与提取元数据 |
| rule_version_documents | 规则版本与多份来源文档的关联 |
| rule_engine_state | 唯一活动版本、激活时间和并发发布修订号 |

ID 由应用生成 UUID 字符串。时间统一按 UTC 写入。
规则使用 SQLAlchemy 通用 JSON 类型；原始字节对应 LargeBinary。其余字段使用通用 ORM 类型，保持 SQLite 测试兼容性。

## 版本与证据

- 一个版本保存完整规则集，首期不实现逐条规则表和复杂补丁合并。
- 规范化规则 JSON 后计算 SHA-256，作为 `version_id`；规范化须固定键排序、编码和序列化方式。
- 文档以原始下载字节计算 SHA-256，同一来源相同内容仅保存一次。
- 相同文档再次抓取时不修改历史记录；本次检查结果记录在同步任务摘要及来源检查时间中。
- `extraction_metadata` 应包含模型标识、Prompt 版本等；来源证据与规则 ID 的映射保存在验证报告或提取元数据中。
- `validation_report` 保存结构、证据及回归检查结果；其 JSON 契约在实现阶段统一。
- 原始资料只允许从指定来源采集，采集端限制文件大小、请求超时和重试次数。
- 批准后的规则内容不可修改；历史版本及文档不得删除。新增内容创建新版本，重复规则内容复用已有版本。

## 发布和回滚

1. 校验目标版本状态为 APPROVED。
2. 在同一事务内，以读取到的 revision 为条件更新 rule_engine_state，递增 revision 并记录激活时间。
3. 更新行数必须为 1，否则并发发布冲突，重新读取后处理。
4. 事务提交后刷新内存快照；加载失败时明确报错，不能将旧版本伪装成新版本。
5. 多进程部署时，每次审核前检查 revision，变化后加载完整快照；每次审核固定实际加载的版本。
6. 回滚复用相同流程，将活动指针切回历史批准版本，revision 仍然递增。

启动时没有活动版本则拒绝执行审核。同步或 AI 提取失败不改变当前活动版本。
抓取和模型调用期间不持有数据库事务或连接，读写阶段使用短事务。
同步任务中断后可能遗留 RUNNING 状态，实现时需提供超时任务恢复机制。

## 索引

| 索引/约束 | 查询或用途 |
| --- | --- |
| rule_sources.url UNIQUE | 来源去重 |
| rule_documents(source_id, content_hash) UNIQUE | 文档去重 |
| rule_documents(source_id, fetched_at) | 来源最新资料与历史 |
| rule_documents(sync_run_id) | 同步任务产生的文档 |
| rule_versions(status, created_at) | 候选队列和历史批准版本 |
| rule_version_documents(document_id) | 文档反查规则版本 |
| rule_sync_runs(started_at) | 最近任务列表 |

主键与唯一约束已有索引，不重复创建。首期按版本整包加载，不对 JSON 内容建立索引。

## 约束边界与后续实现

DDL 已包含主外键、状态检查、时间检查和活动状态单行约束。
应用层负责 JSON 结构、哈希正确性、批准后内容不可修改、合法状态转换，以及只允许批准版本激活。
当前活动指针只保存最新发布状态；若后续要求逐次发布操作审计，应新增发布事件表。

当前交付仅为设计和 SQL，尚未创建 ORM 模型、迁移或数据库表，也未验证 PostgreSQL 执行。
后续新增模型应放在 backend/models/，继承现有 Base；迁移通过 Alembic 生成并在 SQLite 和 PostgreSQL 验证。
