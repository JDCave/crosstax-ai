# 异步规则验证任务设计与接口

主流程仍管理 AuditSession/session_id，规则引擎管理一次输入的一次 task_id。
补正后新建任务，不覆盖旧结果；规则任务不是完整审核 case 状态机。

## 契约

- POST /api/v1/rule-engine/tasks：Idempotency-Key 必填，body 为 session_id(UUID)、deadline_at(可选带时区时间)、validation(现有校验请求)。保存事务成功后返回 202、Location 和任务状态。
- GET /api/v1/rule-engine/tasks/{task_id}：返回状态、result/error、建议轮询间隔。完成时 result 是现有完整 ValidationResponse；不要求上游直接查 DB。
- 保留旧同步 /validate 调用作为兼容入口，从 Swagger 隐藏；公开文档展示两个上游任务接口与一个前端报告下载接口。

状态 PENDING → RUNNING → SUCCEEDED/FAILED。SUCCEEDED 表示执行成功，不代表 AUTO_PASS。
提交仅检查请求结构；TIN、缺签等业务问题由 Worker 生成 SUCCEEDED + NEED_USER_FIX。
AI 补正降级不把已经完成的规则检查变成 FAILED。
同幂等键、相同规范输入返回同任务；不同输入 409。原请求未指定截止时间时，重试也不重新计算输入身份。
未知任务 404；过期内容 410；容量满、缺少加密配置或规则不可用 503，带 Retry-After。

## 版本与执行

提交固定规则 JSON/版本/revision、表单策略完整快照和引擎构建标识，一起加密保存。
Worker 只使用保存的快照，不能 refresh 当前规则替换原任务依据；构建变化拒绝执行旧任务，要求原构建或重新提交。
独立 CLI Worker，无每请求后台线程、无 Redis/Celery；核心无副作用验证可在线程池运行，模型使用现有 async HTTP。
不在执行或模型等待期间持有数据库连接。

任务表使用 claim token、租约和尝试次数；领取、续租、完成均条件更新。
失去租约的旧 Worker 不能写成功或失败；租约过期可有限重领，保证的是至少一次尝试与终态提交防覆盖。
结果和 SUCCEEDED 同事务；Worker 意外退出后，后继 Worker 可以恢复待处理或过期租约任务。
截止时间按 min(上游 deadline_at, 接收时刻+服务器上限) 固定，排队及执行都计入；默认上限 30 秒。
上游必须传整条链路剩余截止时间，不能在 Vision 后重新计满 30 秒。
终止线程池等待不能强行杀死 Python 线程，计算必须无写副作用；最终数据库写入由租约 token 和截止条件防护。

## 存储与容量

新增 rule_validation_tasks 与单行 rule_task_queue_state；后者串行化入队容量检查，使用 ORM 条件更新，兼容 SQLite/PG。
输入、规则快照和结果采用 cryptography 的 Fernet 认证加密，密钥只在环境配置，不入 DB。
支持主密钥加旧密钥解密，轮换期间保留未过期任务所需旧密钥。幂等摘要使用密钥 HMAC，不用明文表单作索引。
session_id、任务状态、时刻及规则版本属于明文运行元数据，不等于所有元数据匿名化。
默认保留 24 小时；Worker 定期清除过期密文，保留幂等 tombstone，过期任务不复用键重新执行。
GET 不返回过期内容，即使清理 Worker 尚未运行。清理需要持续运行 Worker 或显式 cleanup 命令。
密钥缺失时仅异步 API 返回 503，旧同步接口仍可使用。

## 运行与迁移

先升级 Alembic，再配置 RULE_TASK_ENCRYPTION_KEYS(JSON 数组，首项用于加密)、启动 API 与独立 Worker。
使用现有依赖 uv 管理；新增 cryptography 是本方案认证加密的实现依赖，不自行编写加密算法。
服务按内部可信主后端调用；用户鉴权和 session 归属授权仍由主后端/网关负责，不能当作公网匿名服务。
按现有连接上限分配：建议 API DATABASE_POOL_SIZE=2，Worker=1，总共不超过 3，均 max_overflow=0。
迁移以已有六张基础规则表与历史迁移为前置条件；新库用 bootstrap_rules.sql 建立基线。
validation_engine.sql 当前是完整十一表快照，不能再与 upgrade 重复执行。路径见[数据库说明](../infrastructure/db/README.md)。不自动激活未知规则。

## 分阶段验收

1. 文档先提交。
2. 存储、加密和队列仓储：迁移、幂等、容量、过期、租约/token 条件、加密及轮换。
3. API/Worker：请求落库后返回、独立执行、固定快照、心跳恢复、失败、查询及整体集成。
4. 更新 OpenAPI、样例、进度、部署命令与完整测试后提交；不自动启动生产 Worker 或安装任务。

结构错误不回显原始输入；Worker 错误只保存固定错误码，不保存异常正文或模型原文。
新结果和任务数据的保存策略与旧可选归档表不同，不能据本功能宣称旧归档已加密。

## 已交付实现（2026-11-08）

- models/rule_validation_task.py、models/rule_task_queue_state.py：新增两表和领取／保留／会话索引。
- core/rule_tasks.py：认证加密、HMAC、环境配置；infrastructure/rule_tasks.py：短事务入队、claim、renew、finish、cleanup。
- services/rule_tasks.py：幂等与截止控制、规则／策略／构建固定；services/rule_api.py：共用固定快照执行适配器。
- api/routes/rule_tasks.py 与 api/schemas/rule_tasks.py：提交 202、查询状态和原完整结果；旧 validate 隐藏但保留。
- workers/rule_tasks.py：独立进程、核心线程池、异步 Agent、心跳、恢复和安全错误；连接池固定 1。
- 迁移 20261108_rule_tasks 由 Alembic 比较元数据自动生成，接续 20261103_rule_history；SQLite CLI 升降级已验证。

结构化保存省略原契约禁止的显式 null，并从 JSON 重新校验，避免序列化默认值破坏回放。
结构化任务缺失冻结策略时直接失败，不允许悄悄读取当前策略补齐。
提交等待同样受总时间预算约束；提交超时无法承诺未提交，应保留原键重试。
常驻 Worker 遇存储异常固定提示后重试；失去租约时停止当前等待，不允许旧执行写入。
清理 Worker 每轮最多 100 行，显式 --cleanup 循环清理所有过期批次，保留元数据 tombstone。
模型补正保存实际输出与调用统计，模型文本不承诺逐字可复现；固定快照保障确定性规则依据。

[API、配置与运行命令](../api/RULE_TASKS_API.md)；自动化验证覆盖并发容量、幂等、Case A–E、三份结构化任务、加密轮换、失租恢复、超时与脱敏。
未部署生产 Worker 或验收真实百炼请求。后续已按用户授权完成本地 PG 增量升级及隔离集成测试，验收记录见[数据库说明](../infrastructure/db/README.md)。

## 持久化报告联动

成功提交在同一事务建立 PDF 报告待办，具体状态和存储见 [报告设计](PDF_REPORTS.md)。
查询返回独立 report_status/report_error；报告 READY 时才提供 report_url，规则 result 不等待 PDF。
Worker 内两个循环共享一连接池，报告不占用规则 30 秒预算；公共入队容量同时计入待生成报告，限制下游积压。
默认新后台循环会生成并保存 PDF，下载只读已生成文件。
