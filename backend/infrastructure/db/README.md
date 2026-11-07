# 规则引擎数据库

本目录以当前 SQLAlchemy ORM 模型和 Alembic 历史为依据，不另维护一套手写数据库设计。
数据库为 `devdb`，规则引擎表统一在 `crosstax` schema。当前共 **11 张表**。
主后端的 AuditSession/Merchant 尚未落地；队友的 `users` 示例模型不属于规则引擎，不在这些 SQL 中创建或删除。

## SQL 文件与唯一来源

| 文件 | 内容与用途 | 来源 |
| --- | --- | --- |
| [validation_engine.sql](validation_engine.sql) | 当前完整 11 表、索引、约束和协调初始行；空 schema 建库参考快照 | 当前 ORM 元数据 |
| [bootstrap_rules.sql](bootstrap_rules.sql) | 历史六表基线；仅用于空库进入现有迁移链 | 当前六个基础 ORM 模型 |
| [rule_pdf_reports.sql](rule_pdf_reports.sql) | 报告生成队列及 PDF 密文表的增量评审稿 | 迁移 20261108_pdf_reports |
| [rule_validation_tasks.sql](rule_validation_tasks.sql) | 仅异步任务两表及索引的增量评审稿 | 迁移 20261108_rule_tasks |

完整快照已替换原先只有六表的过时 `validation_engine.sql`。
六表基线保留在用途明确的 bootstrap 文件，因为已发布的第一份迁移以它们存在为前提。
任务增量稿便于审阅，**不是**完整建库快照或迁移后的额外执行步骤。
四个文件均自动生成，不手工修改；运行代码不执行这些 PG SQL，业务持久化仍通过异步 ORM。

```bash
uv run python -m backend.cli.schema_sql --write  # 更新全部 SQL，仅写文件，不连接数据库
uv run python -m backend.cli.schema_sql --check  # 检测与模型／迁移不一致，默认也是检查
```

模型变化仍必须有经过评审的 Alembic 迁移；刷新 SQL 快照不能代替迁移，也不能升级已有表。
版本链：`20261103_rule_history` → `20261108_rule_tasks` → `20261108_pdf_reports`（当前 head）。
不删除或改写已发布迁移；它们是升级和回退所需历史，不是过时设计垃圾。

## 当前数据表

| 表 | 职责和边界 |
| --- | --- |
| rule_sources | 允许采集的官方来源、法域、启用状态、HTTP 缓存及检查时刻 |
| rule_sync_runs | 资料同步状态、摘要、错误和起止时刻；不是验证任务 |
| rule_documents | 原始资料字节、正文、来源和内容 SHA-256；抓取不等于结构化规则提取 |
| rule_versions | 整包规则 JSON、内容版本、候选／批准／拒绝状态及验证元数据 |
| rule_version_documents | 规则版本与多份资料证据的关系 |
| rule_engine_state | id=1；活动规则版本、激活时刻及发布 revision |
| rule_publications | 追加式发布事件：目标／前一版本、revision、操作人、原因 |
| rule_audit_records | 旧单税籍内部归档／重放信封；原 JSON 字段未加密，不替代主 AuditSession |
| rule_validation_tasks | 异步输入／规则／策略快照及结果密文、HMAC 请求摘要、状态、截止、租约和尝试次数 |
| rule_pdf_reports | 独立报告状态、租约、有限重试、模板／构建标识和加密 PDF 文件、校验摘要及长度 |
| rule_task_queue_state | id=1；短事务串行化入队容量检查，应用可按需初始化 |

规则源导入只做允许来源的资料同步；结构化候选包由上游提供。
候选规则经证据、回归和审批门禁后才能激活；不在本引擎内使用 AI 自动提取或批准规则。
每次验证固定规则版本；新异步任务还固定表单策略和构建标识，不随当前活动规则变化。

## 部署路径：选择一种

所有操作前先确认 `DATABASE_URL` 指向目标库并备份。以下说明覆盖三种路径；本轮按用户授权仅对本地 devdb 执行缺失的增量迁移，未重建已有表。

### 已有六表或历史表：优先迁移

```bash
uv run alembic current
uv run alembic upgrade head
```

迁移记录必须与实际表结构相符。若之前手工建过历史／任务表但没有对应版本记录，先核对字段、约束和索引再协调 Alembic 版本，不能直接 upgrade 或盲目 stamp。
不要重跑完整快照、bootstrap 或相同的增量 SQL；它们会与已有表冲突。
`CREATE TABLE` 未加 IF NOT EXISTS，避免把结构不一致的旧表静默当作升级成功。

### 空数据库：基线加迁移（推荐）

连接 `devdb` 后执行 `bootstrap_rules.sql`，创建 schema、六张基础表和活动状态初始行，再迁移：

```bash
psql -h localhost -p 5432 -U devuser -d devdb -v ON_ERROR_STOP=1 \
  -f backend/infrastructure/db/bootstrap_rules.sql
uv run alembic upgrade head
```

口令由本地环境／交互提供，不写入命令或仓库。
这条路径由 Alembic 创建两张历史表、两张任务表和一张报告表，并正常维护版本记录。
初始没有活动规则，需要使用现有发布流程注册、批准和激活规则，不能直接校验。

### 空 schema 完整快照：手工部署替代

`validation_engine.sql` 一次创建全部十一表和协调行，仅用于空规则 schema。
它不会创建数据库本身，也不创建 `alembic_version`、User 或主审核业务表。
该脚本与“bootstrap + upgrade”二选一，不能接着 upgrade 重建相同表。
若团队选择此路径，完整事务成功并核对其与 `20261108_pdf_reports` 一致后，才可在同一目标数据库执行 `uv run alembic stamp 20261108_pdf_reports`，登记对应迁移版本。
不能对任意已有库直接 stamp head，也不能用完整 SQL 修复旧库差异。

任务增量 SQL 同样不会维护迁移版本；仅供对应增量的团队手工部署审阅，不作为默认部署步骤。
所有 SQL 都不含 DROP/TRUNCATE；清理的是仓库中的过时设计说明，不删除任何实际数据表或历史数据。

## 约束与索引

精确列定义、空值、默认值、外键、CHECK 和索引以生成 SQL／ORM 为准：

- 来源 URL 唯一；资料 `(source_id, content_hash)` 唯一；索引支持来源历史和同步任务反查。
- 规则版本按 `(status, created_at)` 索引；证据关系按 document_id 反查。
- 发布 revision 主键；活动状态和队列状态各限 id=1。
- task_id 主键、idempotency_key 唯一；任务领取索引 `(status, lease_until, created_at)`、过期索引 expires_at、会话索引 `(session_id, created_at)`。
- 规则内容哈希、JSON 契约、批准后不可变、合法状态转换和 token/lease 防覆盖由应用负责；数据库管理员不受 ORM 不可变保护约束。

不额外建立 JSON 内容索引或重复主键／唯一索引。时间按 UTC 写入；UUID 和内容哈希由应用生成。

## 运行与保存边界

业务连接统一由 `backend/infrastructure/database.py` 管理；API 建议最多 2 连接，独立 Worker 固定 1，均禁止 overflow，合计不超过 3。
额外 API/Worker 进程、迁移和后台发布同样计入连接预算。
计算、网络和模型等待不持有数据库连接，事务保持短小；SQLite 使用 schema_translate_map，PG 保留 crosstax。

异步输入、完整依据、结果及持久化 PDF 采用 Fernet 认证加密，密钥只在环境变量，支持轮换；幂等摘要采用 HMAC。
状态、session_id、时刻和版本属于明文运行元数据，旧 rule_audit_records 的原 JSON 未纳入加密改造。
默认保留 24 小时，到期查询 410，输入／结果及 PDF 密文由 Worker 两个循环或手动 cleanup 清理，保留幂等 tombstone。
主会话、原始用户文件及授权仍由主后端负责。

接口、密钥、Worker 与超时见 [异步 API 文档](../../api/RULE_TASKS_API.md)，规则发布见 [更新手册](../../engine/RULE_UPDATES.md)。
自动化测试验证 SQL 生成一致性及 SQLite／PostgreSQL 迁移；配置 CROSSTAX_TEST_DATABASE_URL 后，PG 用例仅使用随机隔离 schema。未配置时四项 PG 用例跳过。


## 本地同步验收记录（2026-11-08）

用户授权同步的目标为 localhost:5432/devdb，规则 schema 为 crosstax。
升级前为八表、版本 20261103_rule_history；只读比较确认仅缺两张任务表及三个普通索引。
执行 `alembic upgrade head` 后，版本为 20261108_rule_tasks，共十表；任务幂等唯一约束及三个普通索引均已存在。
Alembic 与 ORM 比较（含类型／默认值／索引／外键等支持项）无差异，原八表行数保持不变，未删除原有数据或修改活动规则。
新任务表为空，队列单行由应用首次入队按需创建；未启动 Worker 或生成任务密钥。
真实本地 PG 隔离测试已运行：全量 276 项通过、无跳过；测试 schema 已清理。
此记录不代表云端数据库、真实百炼或完整上传审核链路已经部署或验收。


## 报告持久化升级记录（2026-11-08）

新增 Alembic 20261108_pdf_reports，生成 SQL 为 rule_pdf_reports.sql；完整快照现为十一表。
本地 devdb 已应用这份增量迁移，只新增报告表和领取索引，不修改原十表数据。
规则结果成功与报告 PENDING 行同事务提交；READY 与密文同事务保存，下载不再实时渲染。
报告密文包含独立域前缀，沿用共享 Fernet 轮换密钥；GET 查询只读取报告元数据，不加载 PDF 文件。
Worker 两个循环共用一连接池，缺失的历史成功报告自动补建，已生成的文件不自动重写。
修复故障后可使用 `uv run python -m backend.workers.rule_tasks --retry-report 任务UUID` 重新排队仍在保留期内的 FAILED 报告；READY 和过期任务拒绝重排。
全量 294 项测试通过，包含 PG 与 Worker CLI；源 SQL 一致性、Ruff 和 mypy 通过。阿里云部署和主系统授权仍待队友接入。
