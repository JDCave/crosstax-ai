# ADR-008: 混合数据库方案（SQLite 开发 + PG 生产）

## 状态
已采纳 (2026-10-23)

## 背景
本地开发机无法直连阿里云 PG（仅 ECS 内网可达），需选择数据库方案。

## 决策
采用混合数据库方案：本地开发使用 SQLite（零配置），生产/测试环境使用阿里云 PG 16。

## 否决方案
- **全程 PG**：本地无法直连阿里云 PG（外网不可达），开发体验差
- **全程 SQLite**：生产环境与开发环境差异大，可能隐藏兼容性 bug

## 理由
- SQLite 零安装零配置，本地开发迭代快
- PG 16 生产环境保证数据一致性和并发能力
- 通过 SQLAlchemy 2.0 异步 ORM 屏蔽底层差异
- 后端切换只取决于 `DATABASE_URL`，无需改动业务代码

## 后果
- 数据库抽象层：`backend/infrastructure/database.py`（`create_async_engine` + `async_sessionmaker`）
- 连接 URL 必须带异步驱动前缀：`sqlite+aiosqlite://`（本地）/ `postgresql+asyncpg://`（PG）
- 配置由 `backend/core/config.py` 的 `DatabaseSettings` 管理，环境变量前缀 `DATABASE_`（`DATABASE_URL` / `DATABASE_POOL_SIZE` / `DATABASE_MAX_OVERFLOW` 等）
- 缺省 `DATABASE_URL=sqlite+aiosqlite:///./crosstax.db`；显式设置为 PG URL 即切换后端
- `ENVIRONMENT`（dev / test / prod）仅控制日志与调试开关，不参与数据库后端选择
- 禁止使用 PG 特有语法（如 `ILIKE`、`::` 类型转换）
- 连接池限制：每人 ≤ 3（总连接上限 30），详见 ADR-010
- 迁移工具：Alembic（双后端均可生成 migration script）
