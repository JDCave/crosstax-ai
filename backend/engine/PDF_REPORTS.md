# 持久化异步 PDF 报告设计

## 已确认的方案

规则校验完成后自动创建报告待办，后台生成 PDF 并加密保存在 PostgreSQL。
下载只读取已保存的 PDF，不触发渲染、不重跑规则、不调用 AI。
目前只有 API 和 PG 资源，优先复用阿里云 RDS；将来可将文件存储替换成私有 OSS，保留同一元数据／下载接口。
报告是规则引擎校验报告，不冒充尚未实现的主 AuditSession 全流程最终裁决。

## 三条 API 与状态

- 上游后端 POST tasks：提交规则校验。
- 上游后端 GET tasks/{task_id}：读取 JSON 结果及 report_status/report_error/report_url。
- 前端 GET tasks/{task_id}/report：仅下载已生成且未过期的报告。

校验状态与报告状态独立。规则 SUCCEEDED 立即可消费 JSON，不等待 PDF。
报告状态为 PENDING → RUNNING → READY / FAILED，有限重试期间回到 PENDING。
任务未成功时 report_status 为 null；成功但历史报告待补建时视为 PENDING。
仅 READY 提供 report_url。主后端拿到规则 JSON 后不必继续阻塞轮询 PDF；前端按 task_id 使用固定报告 URL，生成中按 Retry-After 有界重试，不因 report_url 尚为 null 而永远无法启动下载。

| 条件 | HTTP / code |
| --- | --- |
| 校验 PENDING/RUNNING | 409 REPORT_NOT_READY |
| 校验 FAILED | 409 REPORT_TASK_FAILED |
| 校验 SUCCEEDED，报告 PENDING/RUNNING/历史待补建 | 409 REPORT_GENERATING，Retry-After: 2，提示报告生成中 |
| 报告 READY | 200 application/pdf，返回保存的同一份 PDF |
| 报告最终 FAILED | 503 REPORT_GENERATION_FAILED，不无限自动重试 |
| 任务不存在／过期 | 404 TASK_NOT_FOUND / 410 TASK_EXPIRED |
| 文件损坏／密钥或存储不可用 | 503 安全错误，不回显内容 |

## 数据与事务

新增 ORM 表 rule_pdf_reports，task_id 主键并外键指向 rule_validation_tasks。
保存状态、模板版本、生成构建、密文、PDF SHA-256、字节数、尝试次数、claim token、租约、下次尝试时间、起止时刻及固定错误码。
校验成功的 result + SUCCEEDED + 报告 PENDING 行在同一事务提交，防止提交成功后进程崩溃丢失报告任务。
Worker 补建未过期历史成功任务缺少的报告记录；不覆盖已有 READY 或失败记录。
报告密文与 READY 在同一事务内写入；基于 token、有效租约和父任务到期时间阻止旧 Worker 覆盖结果。
默认最多三次生成尝试，临时失败指数退避；输入／上限／构建等永久错误直接 FAILED。

PDF 使用与任务相同的轮换密钥，通过 Fernet 加密原始 PDF 字节，并使用域前缀隔离 JSON 密文。
文件摘要用于下载一致性核验，不是电子签名；元数据不等于匿名数据。
报告继承父任务保留时间，默认 24 小时。过期查询立即拒绝；清理同时删除输入、结果和 PDF 密文，保留状态与幂等 tombstone。
报告标题、主体、问题、逐项检查、规则出处、执行范围、AI 已保存建议、版本指纹及完整 JSON 附录保留。

## Worker 与连接预算

现有独立 Worker 进程运行两个协程循环：规则校验和报告生成，分别领取各自持久化队列。
二者共享同一个一连接数据库池，API 两连接加 Worker 一连接，不增加总预算。
报告 CPU 渲染在线程执行；不持有数据库连接等待渲染，不阻塞规则校验协程。
每个 Worker 最多一个实际渲染线程；超时或失去租约后，旧线程结束前不启动下一个渲染。
报告使用独立租约和心跳，执行预算默认 15 秒，不重置或占用规则校验 30 秒预算。
入队容量同时计入未完成校验及待生成报告，防止报告积压无限增长。
--once 同时尝试一项校验和一项报告；--cleanup 清除两类过期密文。

## 部署与验证

先执行新增 Alembic 迁移，再部署相同代码及字体的 API/Worker；无新云服务、密钥或管理 API。
内嵌中文字体和 OFL 已随包保存，不依赖宿主机字体或运行时网络。
限制源快照 2 MiB、合计 5000 项问题／检查／税籍、100 页及 8 MiB PDF，超限报告最终失败，不截断。
已有报告保留原模板和字节；新部署不因模板改变重写历史 PDF。
前端经业务网关登录和任务归属校验后下载；规则服务仍不自行提供主系统用户认证。
主后端需把 report_status 转发给前端；整个审核会话的最终裁决仍由主流程汇总。

验收覆盖：事务回滚、规则成功但报告生成中、后台生成后重复下载、下载不渲染、三态结果、生成失败及重试、租约恢复和 fencing、历史补建、到期清理、密钥轮换、SQLite/PG 迁移与完整 HTTP 流程。

## 竞赛本轮不安排的扩展

按用户 2026-11-08 最新决定，以下仅作为历史方案记录，本轮不继续实现，也不作为当前交付待办。

1. 主会话聚合与用户归属授权，接通真正整条审核流水线。
2. 下载审计及任务／报告队列监控、失败告警。
3. 大规模和长期留存改用私有 OSS，PG 仅保留元数据，使用短期签名地址或服务转发。
4. KMS 管理密钥和真实报告签名；当前摘要不能替代签名。
5. 精简阅读版与完整证据附件分层，提升人工阅读体验。

## 交付验证与运行

rule_pdf_reports 已由自动生成迁移 20261108_pdf_reports 创建；SQL 快照与数据库说明同步为十一表。
294 项测试全部通过，包含 SQLite/PG 迁移、原子回滚、生成中下载、重复存储读取、失败重试、失租防覆盖、历史补建、过期清理、字体和独立 Worker CLI。
本地 devdb 已仅应用增量迁移；原十表数据保留。未启动生产常驻进程、未部署阿里云网关／用户授权。
内部 CLI --retry-report 任务UUID 可在故障修复后重排未过期的 FAILED 报告，不覆盖 READY，不重跑规则。
完整命令和前端有界重试示例见接口文档。

## 竞赛解释卡片扩展

经用户新增授权，报告模板 v2 将已保存的 explanation_cards 中的补正动作及来源加入问题区。
展示层不修改 verdict,不重新请求 Agent；旧 READY 文件不自动重写。任务 compare_to 为临时展示,不混入固定 PDF 快照。
表结构仍十一表,初始化 API 和本地种子同步见 [竞赛设计](COMPETITION_FEATURES.md)。
