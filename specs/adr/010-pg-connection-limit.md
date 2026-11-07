# ADR-010: PG 连接池限制（每人 ≤ 3）

## 状态
已采纳 (2026-10-23)

## 背景
组委会限制阿里云 PG 账号连接上限 30，建议连接池 5-10/人。4 人团队需合理分配。

## 决策
团队约定每人连接池 ≤ 3，总计 12 连接，留有余量应对突发。

## 否决方案
- **按建议 5-10/人**：4×10=40 超限，4×5=20 接近上限无余量

## 理由
- 4×3=12 连接，远低于 30 上限
- 留 18 连接余量应对演示突发流量
- 竞赛场景并发低，3 连接足够

## 后果
- 配置项位于 `backend/core/config.py` 的 `DatabaseSettings`：`pool_size=3, max_overflow=0`
- 引擎在 `backend/infrastructure/database.py` 由上述配置构建
- 环境变量 `DATABASE_POOL_SIZE` / `DATABASE_MAX_OVERFLOW` 可覆盖，`.env.example` 已按本决策给出缺省值
- 禁止溢出连接（`max_overflow=0`），避免超限
- 本地 SQLite 开发不受此限制影响

## 实现状态
- 2026-11-02：初始脚手架曾按通用缺省值实现为 `pool_size=5, max_overflow=10`（单人可开 15 连接，4 人 60 连接，超组委会上限一倍），已回归本决策的 3/0，并由 `tests/backend/test_config.py` 断言锁定。
