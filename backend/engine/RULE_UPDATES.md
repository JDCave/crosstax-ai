# 后台规则更新与发布设计

## 目标与边界

不新增发布 UI 或对外 API。现有 `/api/v1/rule-engine/validate` 保持不变。
独立 CLI 由操作系统 cron 每日触发：官方资料检查 → 接收上游结构化规则包 → 验证及影响分析 → 受控发布。
不实现 PDF/OCR/HTML 正文提取，不让补正 Agent 修改规则或批准发布。
当前官方资料导入器仅允许已配置的 OECD 来源，不宣称自动覆盖全部目录国家。

## 分阶段交付

1. 文档：明确候选包、影响分析、自动发布门禁、单机锁、定时运行和失败行为。
2. 影响分析：比较同一业务样本在旧／新快照下的确定性结果，输出结构变化、裁决变化、覆盖或验证深度退化和报告指纹；提供离线 CLI。
3. 更新编排：复用资料导入、候选注册、回归门禁、批准状态、CAS 激活及发布历史；不自动审批 AI 候选。
4. 运行：单机文件锁防重叠，运行摘要写现有同步记录，提供 cron 模板与联调测试。
每阶段测试后单独 commit，不自动 push，不安装 cron 或执行真实发布。

## 影响报告

输入：基准规则、候选规则、样本、业务日期、基准 revision。
所有样本使用同一策略，各版本只编译一次；支持单／多税籍，不调用 AI。
输出：版本与构建指纹、样本集指纹、规则增加／删除／修改、执行字段和资料字段区别、
逐案例裁决与检查深度变化、风险原因、报告指纹。
不输出姓名、日期、地址、税号或上游自由文本；case_id 应为非敏感测试标签。
当前演示默认使用 Case A–E，这只是所给样本的影响，不等于真实商户总体影响评估。
既有 TIN 回归门禁独立执行，不能由影响报告替代。

自动发布硬阻断：删除选择器、降低验证深度、移除原有阻断（即使被其他阻断掩盖）、出现通过到阻断或更宽松裁决、样本检查深度退化。
新增覆盖或其他已知结果变化也必须由可信策略精确批准报告指纹，不能仅因测试通过自动认定税法正确。
仅资料说明等非执行字段变化时，只保留资料检查记录，不切换活动规则。

## 上游候选包（JSON）

- schema_version：1。
- base_version_id：候选基于的当前规则哈希，防止陈旧补丁覆盖新版本。
- rules：完整规则快照，不是增量补丁。
- documents：资料引用列表，每项 document_id、content_hash。
- regression_cases：可选，自定义规则所需的回归样本；已批准版本使用其原审批时保存的样本。

同一规则哈希已活动时幂等结束，不生成新版本或重复发布。
引用资料必须存在、哈希匹配且来源启用。自动发布还要求变更规则的官方来源有对应最新资料证据。
抓取结果有部分失败时停止后续发布，保持活动版本。
资料改变但尚无结构化候选包时记录等待上游，不伪造转换结果。

## 可信发布策略（本地 JSON）

- schema_version：1。
- approvals：精确批准项列表，每项 base_version_id、candidate_version_id、impact_hash、evidence_hash。

策略文件由维护者控制，是部署信任边界，不接受上游规则包内的 trusted=true 等自我声明。
候选必须已经通过现有 approve CLI 成为 APPROVED，并通过本次回归、证据和影响检查。
须显式传 --publish 和 --policy 才允许后台激活；默认仅检查并登记候选。
批准指纹绑定业务日期、样本、引擎构建、基准 revision 和候选内容，任一变化需重新确认。
策略不是数字签名；拥有部署文件或数据库管理权限的人仍可绕过应用边界。

## 持久化与并发

复用 rule_documents、rule_versions、rule_sync_runs、rule_publications、rule_engine_state，不新增表。
整体更新任务建立独立同步记录，资料导入器自己的抓取记录另行保留。
成功、等待、拒绝或异常均有摘要；异常只记录类型和固定原因，不回显资料正文或表单。
激活继续复用 CAS revision，版本及发布事件在同一事务写入。
批准不等于自动发布授权：两者必须同时满足。

CLI 文件锁适用于同一机器、同一共享锁路径的定时任务；不宣称分布式锁。
同机重叠立即跳过；跨机器最终发布仍由 CAS 防止丢失更新，抓取重叠需部署单独安排。
锁持有覆盖整个任务，进程退出由操作系统释放，不依赖 PID 文件是否残留。

## 调度与故障

提供 cron 示例，每天执行一次，不把 scheduler 放入 FastAPI lifespan，避免多 worker 重复调度。
cron 使用部署机器时区，维护者需确认与业务时区一致；业务日期按 CLI 指定时区计算。
示例需修改部署目录、Python 路径、候选包及策略路径，不自动写入用户 crontab。
抓取错误、缺候选、候选未审批、无可信策略、证据不足、影响风险、回归失败或 CAS 冲突时均不改变活动规则。
无初始活动版本时要求使用现有审批／激活流程建立基准，不自动引导发布未知规则。
数据库故障可能导致最终运行记录无法落库，CLI 仍返回脱敏错误及非零退出码，不伪称审计已保存。

## 验收

离线对比 Case A–E，证明报告无表单明文且不依赖 AI／数据库。
SQLite 集成覆盖候选等待、可信发布、未审批阻断、删除／降级／裁决风险、证据不足、过期基准、幂等重跑、
抓取失败保留旧版、运行记录、CAS 并发冲突及锁重叠。
保留既有测试，更新接口说明入口和详细设计；不修改 PM 所有 specs/、design/、docs/。

## 阶段 2：已实现的离线影响分析

```bash
uv run python -m backend.cli.rule_updates impact \
  --base rules/rules_v1_base.json --candidate rules/rules_v2_patch.json \
  --cases assets/mock-data/cases.json --today 2026-11-04 --base-revision 0
```

stdout 为 JSON 报告，可重定向到 outputs/；不连接数据库、不调用 AI、不修改活动版本。
输入文件上限 1 MiB，样本 1–500 项、case_id 唯一，仅支持显式声明的 demo 包装字段及结构化表单。
impact_hash 对应报告 report_hash；Case E 展示从规则未覆盖转人工复核，到新规则命中后发现错误。
样本预期 verdict 仅为兼容已有 fixture，不参与影响报告的裁决；回归断言仍由独立门禁负责。
报告不会直接输出表单值；请勿把真实个人标识作为 case_id。


## 阶段 3：后台编排已实现

服务入口为 `backend.services.rule_updates.RuleUpdateCoordinator.run()`，下一阶段提供定时 CLI 包装。
候选契约见 [JSON Schema](rule-bundle.schema.json)，独立可信策略见 [JSON Schema](publication-policy.schema.json)。

同一任务内依次检查：资料同步完整成功、有初始活动版本、候选基准匹配、结构编译、影响分析、
资料 ID 和原文哈希、候选登记、真实回归、风险、批准状态、来源证据、独立可信策略、CAS 激活。
计划模式不审批或激活，但会保存资料、候选和任务记录。
整体结果保存在 rule_sync_runs.summary，资料抓取另有自己的同步记录。
PUBLISHED 表示激活已提交；PLANNED/PENDING_APPROVAL/WAITING_FOR_BUNDLE 是正常等待状态。
BLOCKED/CONFLICT/FAILED/NO_ACTIVE_RULES 记录为同步失败，便于调度监控。

可信批准除版本和 impact_hash 外，还绑定 evidence_hash，避免批准报告后替换资料引用。
evidence_hash 对按 document_id 排序的 document_id/content_hash 计算；资料 URL 和地区须匹配变更规则来源。
引用原文会重新计算 SHA-256；来源须启用，且引用当前同步返回的资料，或唯一可确认的最新存储资料。
时间戳相同且无法确定最新版本时，不猜测顺序，要求重新同步。
已批准版本不补写或篡改历史资料关联；本次证据通过任务摘要和发布 reason 中的哈希关联。
候选包的回归样本用于未审批计划；已批准版本使用其原审批保存的样本，激活时再次执行。

最终摘要与激活不是一个长事务。激活及发布事件已提交后，如最终摘要因数据库故障保存失败，
不会伪称已回滚，需查询发布历史确认；重复运行活动候选哈希相同时会幂等结束。
已知 source importer 错误摘要改为异常类型，避免保存原始网络错误内容。
本阶段 SQLite 与全套验证：217 项通过、3 项 PostgreSQL 按环境跳过；无真实发布操作。

若检测到新资料、上游却仍提供旧活动规则和旧资料引用，结果为 WAITING_FOR_BUNDLE，不会伪称资料已经完成规则转换。


## 阶段 4：定时 CLI 与运行手册

### 一次性准备

使用现有数据库表；本轮没有迁移或新增依赖。
确保已有活动规则。若没有，使用已有 register → approve → activate CLI 建立基准，不能由任务自动批准初始版本。
注册需要检查的官方来源：

```bash
uv run python -m backend.cli.rule_sources --manifest assets/rule-sources/oecd.json
```

该 manifest 当前仅配置 CN/HK/SG 的 OECD 资料，不能将本任务描述为全球所有来源的自动更新。
上游负责把已经提取、核实的资料转换为完整规则包，并提供数据库 document_id/content_hash 引用。
候选包结构示意如下；占位符和空 rules 必须替换，不能直接执行：

```json
{
  "schema_version": 1,
  "base_version_id": "<当前活动版本 SHA-256>",
  "rules": {},
  "documents": [
    {"document_id": "<已导入资料 ID>", "content_hash": "<原始资料 SHA-256>"}
  ]
}
```

已有资料由其他上游任务导入时，可显式传 --skip-source-sync。
此模式仅核对最新存储证据，不能声称刚从官网确认了新鲜度。

### 手动触发同一个后台任务

```bash
uv run python -m backend.cli.rule_updates run \
  --bundle incoming/rule-bundle.json --cases assets/mock-data/cases.json \
  --timezone Asia/Shanghai --lock-file outputs/rule-updates.lock \
  --output outputs/rule-update-latest.json
```

默认检查资料和登记候选，不激活。
测试／审核需要精确复现时传 --today YYYY-MM-DD 固定日期；否则按 --timezone 的当前业务日期计算。
同一报告的批准绑定日期；隔日重算得到不同哈希时需要重新确认，不复用过期批准。
资料变化但文件未到达，或新资料尚未被上游规则包引用时，返回 WAITING_FOR_BUNDLE。
源未配置、部分抓取失败、规则风险或门禁失败不会发布。

### 明确审核后允许自动发布

通过现有命令审批候选；全局目录可使用已有回归集，自定义规则需在 review 文件中提供 regression_cases：

```bash
uv run python -m backend.cli.rule_engine approve <候选版本哈希> --report incoming/review.json
```

维护者检查计划报告，在独立策略文件中填写：

```json
{
  "schema_version": 1,
  "approvals": [
    {
      "base_version_id": "<计划的 base_version_id>",
      "candidate_version_id": "<计划的 candidate_version_id>",
      "impact_hash": "<计划的 impact.report_hash>",
      "evidence_hash": "<计划的 evidence_hash>"
    }
  ]
}
```

空白安全模板见 [publication-policy.example.json](scheduling/publication-policy.example.json)。
空 approvals 不会授权任何发布；候选包里的 trusted 字段也不会被接受。
然后运行：

```bash
uv run python -m backend.cli.rule_updates run \
  --bundle incoming/rule-bundle.json --cases assets/mock-data/cases.json \
  --publish --policy config/rule-publication-policy.json \
  --timezone Asia/Shanghai --lock-file outputs/rule-updates.lock \
  --output outputs/rule-update-latest.json
```

风险被硬阻断时，可信策略不能绕过门禁，需维护者使用现有显式人工发布流程审查处理。
--publish 未传 --policy 会在解析参数时拒绝；旧版本始终保留，不自动重写／删除历史。

### 每日调度

提供 [cron 模板](scheduling/rule-updates.cron.example)，默认每天机器时区 02:00 检查并生成计划。
先创建 outputs/、替换所有部署路径，使用服务账户安装；本次开发没有安装或修改任何 crontab。
默认模板不发布，允许已审核升级时显式增加 --publish --policy。
--timezone 只控制审核日期，不能改变 cron 自身触发时区；需确认机器时区与预期一致。
不要同时在 FastAPI 多 worker 或多台服务器重复安装任务。

文件锁覆盖输入读取、资料检查、数据库流程与输出；同一机器所有调用须使用同一个绝对锁路径。
Linux/macOS flock 非阻塞获取，进程退出由 OS 释放，锁文件保留而不删除，防止 inode 竞争。
锁路径不能是符号链接；同机重叠返回 SKIPPED_LOCKED，不读取上游输入或覆盖上次报告。
这不是分布式锁；最终跨进程发布由 CAS revision 防止丢失更新。
强制终止进程可能留下 RUNNING 同步记录，需要核查；不能仅凭记录存在判断进程仍持锁。

报告以临时文件、fsync、原子替换保存，失败保留旧文件。
--output 不能指向输入文件或锁；真实发布可能已提交后报告写入失败，stdout 保留实际决策并给出 output_error。
这类错误应核查发布历史，不能声称活动版本已回滚。
任务 summary 不含表单明文，但 case_id 仍应使用非敏感标签；日志和报告由部署账户管理。

### 退出码与状态

| 退出码 | 状态 |
| --- | --- |
| 0 | PLANNED、PUBLISHED、UNCHANGED、METADATA_ONLY 或 SKIPPED_LOCKED |
| 2 | WAITING_FOR_BUNDLE、PENDING_APPROVAL；需要上游资料／审批，也用于 CLI 参数错误 |
| 1 | BLOCKED、FAILED、CONFLICT、NO_ACTIVE_RULES，输入读取／报告保存失败 |

默认只输出脱敏 JSON。输入校验异常不回显 Pydantic 原始值。
整体更新审计在任务启动后建立；参数或输入解析失败可能尚未进入数据库任务，此时只返回脱敏 CLI 错误。
当前只提供日志／报告与状态码，不发送邮件或消息，也不新增管理 API。

### 验证记录

自动化使用 SQLite 和模拟 HTTP，覆盖完整资料导入 → 门禁 → CAS 发布 → 同一 loader 热加载流程。
验证旧快照保持不变、新调用读取新版本；锁通过独立子进程验证，原子报告失败保留旧内容。
保留 Case A–E、既有 API 和所有回归测试；本轮不需要前端更改。
真实 PostgreSQL、官网定时抓取、上游规则转换和实际 cron 安装未在本机执行，不能把模拟联调当作生产部署。

最终验证：227 项通过、3 项 PostgreSQL 按环境跳过；Ruff 和新增模块 Mypy 通过，CLI help、契约快照和离线 Case A–E 命令通过。仓库当前没有 frontend/，不执行 npm test。
