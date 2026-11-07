# Validation Engine 数据层设计

本目录保存规则引擎的数据层设计和 PostgreSQL 建表评审稿。
`validation_engine.sql` 是六张基础表的历史初始化脚本，用户此前已执行；不是本次异步功能的完整初始化文件。
新增异步任务的增量建表语句见 [rule_validation_tasks.sql](rule_validation_tasks.sql)，由 Alembic 迁移生成，包含两张任务表及索引；正式部署优先使用迁移。
PostgreSQL 数据库名为 `devdb`，schema 为 `crosstax`。执行 SQL 前需连接 `devdb`；脚本包含 `CREATE SCHEMA IF NOT EXISTS crosstax`。SQL 显式限定所有表、索引目标表、外键及初始数据的 schema，不依赖连接的 search_path；执行账号需要具备相应建表权限，schema 不存在时还需要创建 schema 的权限。

复用现有 `backend/infrastructure/database.py` 的数据库连接与会话，API 复用原连接池，独立 Worker 使用同一数据库抽象创建一连接池。
连接预算应遵守 ADR-010：API pool_size=2、Worker=1，均 max_overflow=0，总共不超过 3。

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

当前已添加六张表的 ORM 模型和 `backend/repositories/rules.py` 数据访问层，并验证本地 PostgreSQL 连通性。数据库表由已有 SQL 创建，本次不会自动重建表或创建 schema。新增两张历史/归档表已有 Alembic 扩展迁移 `20261103_rule_history`，本地已应用。
后续新增模型应放在 backend/models/，继承现有 Base；迁移通过 Alembic 生成并在 SQLite 和 PostgreSQL 验证。


## 本地连接与调用

项目根目录 `.env` 使用 `DATABASE_URL` 配置异步连接；本地目标为 `localhost:5432/devdb`，ORM 表显式指定 `crosstax` schema。
`.env` 被 Git 忽略。若服务主机实际名为 `local`，请修改 URL 主机部分。
数据库配置会读取根目录 `.env`，环境变量优先。

```python
from backend.infrastructure.database import async_session_factory
from backend.repositories.rules import RuleRepository

async def read_active_rules():
    async with async_session_factory() as session:
        repository = RuleRepository(session)
        revision, version = await repository.get_active_version()
        return revision, version.version_id, version.rules
```

写操作使用 `async with session.begin():` 包裹，由调用者提交/回滚；Repository 只 flush，不自行 commit。
`create_candidate` 按规范化 JSON 哈希去重，`review_candidate` 只允许候选转批准或拒绝，`activate` 必须传入预期 revision。
规则结构和测试报告的业务验证由后续引擎服务完成；Repository 不判断报告能否支持批准。
相同内容的重复写入受唯一约束保护；并发采集发生唯一冲突时调用方回滚并重试，首期建议单同步任务运行。
SQLite 测试通过 schema_translate_map 将 crosstax 映射到默认 schema，生产 PostgreSQL 保持显式 schema。


## 追加表与迁移

`rule_publications`：激活历史，主键 revision，外键指向目标和前一规则版本。
`rule_audit_records`：引擎执行信封，主键 session_id，保存输入、上游问题和完整结果，支持幂等与重放。
新环境先按已有流程初始化六张基础表，再执行 `uv run alembic upgrade head` 创建两张历史表及两张异步任务表。
已有六表的数据库只运行迁移，不重新执行原建表 SQL。
迁移前的发布不补造事件；新表不改变原主审核会话模型。
应用层不可变保护见 immutability.py；数据库管理员和 Core 直连不受 ORM 保护。


## 异步任务增量（2026-11-08）

迁移 `20261108_rule_tasks` 接续 `20261103_rule_history`，新增：

| 表／索引 | 用途 |
| --- | --- |
| rule_validation_tasks | 加密请求、冻结快照、加密结果、状态、截止时间、租约及幂等摘要 |
| rule_task_queue_state | 单行状态，串行化容量检查和入队；应用按需初始化 |
| idempotency_key UNIQUE | 同键去重，主键 task_id 已自带索引 |
| ix_rule_task_claim(status, lease_until, created_at) | 领取和租约恢复 |
| ix_rule_task_expiry(expires_at) | 过期清理 |
| ix_rule_task_session(session_id, created_at) | 按主审核会话查任务 |

已有数据库推荐仅运行：

```bash
uv run alembic upgrade head
```

不要重复运行基础 SQL，也不要再手动执行同一迁移对应的增量 SQL。
增量 SQL 仅用于审阅或团队管理的手工部署；手工执行不会更新 Alembic 版本表，后续迁移前必须核对并协调版本记录，不能直接再次 upgrade。
本次未连接或迁移真实数据库。迁移已验证 SQLite 升降级，PostgreSQL 目标环境验证尚待执行。
接口与配置见 [异步 API 文档](../../api/RULE_TASKS_API.md)。
