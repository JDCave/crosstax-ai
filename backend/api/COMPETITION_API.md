# 竞赛能力接口

详细设计见 [竞赛功能设计](../engine/COMPETITION_FEATURES.md)。

- 解释卡片：原任务 result.explanation_cards，沿用既有业务接口与 verdict。
- 补正对比：GET /api/v1/rule-engine/tasks/{新任务UUID}?compare_to={旧任务UUID}，结果附加 comparison；同一主会话且两个任务均成功。
- 模拟升级：GET /api/v1/rule-engine/demo/upgrade-impact，需 RULE_DEMO_ENABLED=true；仅读演示配置，不更新真实规则。
- 初始化：POST /api/v1/rule-engine/setup/initialize，body {}，X-Setup-Token 匹配 RULE_SETUP_TOKEN；仅 RULE_SETUP_ENABLED=true 开放，始终从业务 Swagger 隐藏。

初始化使用现有 DATABASE_URL；数据库本身必须已存在，账号需要 schema/建表/迁移权限。
它会创建/迁移规则表、补齐内置来源与通过回归的 global v4，仅无活动版本时激活；不会清空数据或生成审核任务。
初始化后仍需提供共享 RULE_TASK_ENCRYPTION_KEYS 并启动 `uv run python -m backend.workers.rule_tasks`。
原 PDF 下载路径和 REPORT_GENERATING 重试约定不变。

预期错误：未开启 404；初始化口令不匹配 403；初始化忙碌或数据库结构冲突 409；数据库不可连接/初始化配置无效 503。
对比：同一任务/跨会话 422或409，未完成409，过期410，不存在404。对比不返回字段原始值。

前端：先显示解释卡片；补正提交必须换幂等键，保留相同 session_id；拿新 task_id 对比旧 task_id。
若 comparison 标记不同执行上下文，应提示规则/日期/构建不同，不能宣称完全是用户修复造成。
模拟升级页面必须保留 simulation 标记，不把演示补丁宣传为最新官方法规。

## 初始化调用步骤

在源码或项目 Docker 镜像中运行；镜像已包含 Alembic、规则、Case 和来源 manifest。
先创建好 PostgreSQL 数据库及连接账号，填入 DATABASE_URL。该 API 不创建数据库实例或账号。

配置环境（替换为自己的随机口令；至少 24 字符）：

```dotenv
RULE_SETUP_ENABLED=true
RULE_SETUP_TOKEN=replace-with-a-long-random-setup-token
RULE_DEMO_ENABLED=false
```

重启 API 后，从内部调用：

```bash
curl -X POST http://localhost:8000/api/v1/rule-engine/setup/initialize \
  -H 'Content-Type: application/json' \
  -H "X-Setup-Token: ${RULE_SETUP_TOKEN}" \
  --data '{}'
```

若使用 .env 文件，curl 所在 shell 也需提供对应口令；.env 不会自动成为 shell 环境变量。
成功返回 migration_revision、table_count、sources_added、bundled_rule_version_id、active_rule_version_id、active_revision、active_rule_preserved 和 next_steps。
本地当前为 20261108_pdf_reports、11 张规则表。重复调用新增来源数可为 0，已有活动版本保留。
来源只注册 OECD manifest 元数据，不下载文档；默认 global v4 通过现有回归后才批准，无活动版本时才激活。不会写入虚构原文证据。
迁移与种子分阶段提交；失败后可能已有部分阶段完成，修复原因后重复调用，不盲目 stamp 或手动清表。
初始化结束设置 RULE_SETUP_ENABLED=false 并重启 API。任务加密密钥与 Worker 不会自动创建／启动，按 next_steps 配置现有双循环 Worker。

| HTTP | code | 说明 |
| --- | --- | --- |
| 404 | NOT_FOUND | 初始化或演示开关未开启 |
| 403 | SETUP_FORBIDDEN | 缺少或不匹配初始化口令 |
| 503 | SETUP_NOT_CONFIGURED | 启用初始化但未配置至少 24 字符口令 |
| 409 | SETUP_BUSY | 同机另一初始化正在进行 |
| 409 | SETUP_SCHEMA_CONFLICT | 手工结构、迁移状态或现有列不一致，拒绝猜测或覆盖 |
| 409 | SETUP_RULE_REJECTED / SETUP_ACTIVE_INVALID | 已拒绝默认规则或当前活动规则异常，不自动绕过 |
| 503 | SETUP_FAILED | 数据库／权限／资源配置异常；不回显连接凭据 |

初始化只应在竞赛单实例上开放，单机锁不等于跨主机分布式锁。
旧同步 validate、健康探针和初始化入口继续从业务 Swagger 隐藏；演示入口仅开关启用时额外显示。

## 解释卡片接入

原查询响应 result.explanation_cards，与 issues 一一对应：

```json
{
  "issue_index": 0,
  "title": "签署声明缺失",
  "severity": "BLOCKER",
  "field": "has_signature",
  "reason": "缺少签署声明",
  "action": "核实实际签署情况,补充签署信息后重新提交",
  "action_source": "RULE",
  "origin": "RULE_ENGINE",
  "evidence_refs": ["issue:0"],
  "rule_evidence": [],
  "confidence": 1.0
}
```

上例展示字段结构；reason/confidence 取实际 issue，不由展示层修改。
action_source=AGENT 表示复用已保存并经既有证据验证的 Agent 建议；否则 RULE，展示层不再请求 AI。
rule_evidence 仅关联确实命中该问题的税籍规则，含 jurisdiction_code/rule_id/source_url/verification_level；无出处时不造 URL。
表单签署政策不冒充 TIN 官方规则。FORMAT_ONLY 不能展示成已验证号码签发或归属。
新 PDF 模板 crs-rule-report-v2 包含卡片建议；旧 READY PDF 保持原文件。

## 补正前后对比

1. 保存原 task_id 与 session_id。
2. 补正后使用同 session_id、新 Idempotency-Key 提交新任务。
3. 两个任务 SUCCEEDED 后，调用新任务查询并传 compare_to。

```http
GET /api/v1/rule-engine/tasks/新任务UUID?compare_to=旧任务UUID
```

原 result 和报告状态保持不变，本次响应额外返回 comparison：

- before_task_id / after_task_id、before_verdict / after_verdict。
- context=SAME_CONTEXT 或 DIFFERENT_CONTEXT、context_changes。
- changed_fields：只返回输入变化路径，不返回原值／新值；最多 200 项，另给总数与截断标记。
- resolved / introduced / remaining：问题 code、field、severity、origin 及重复次数 count；各最多 200 种问题，截断明确标记。
- statement：上下文不同的结论不全部归因于用户补正。

上下文缺失时标记 EXECUTION_CONTEXT_MISSING,契约形态不同标记 FORM_CONTRACT,均不能声称纯补正效果。
上下文比较规则内容版本、发布 revision、业务政策、表单策略、任务／执行构建及上游问题；不会重跑旧规则。
不传 compare_to 时 comparison=null。相同任务 422 COMPARE_SAME_TASK，跨会话 409 COMPARE_SESSION_MISMATCH，非成功状态 409 COMPARE_NOT_READY，未知 404、过期 410。
对比不修改历史任务，也不会将临时对比写进先前已保存的 PDF。

## 规则升级演示

设置 RULE_DEMO_ENABLED=true 并重启后：

```http
GET /api/v1/rule-engine/demo/upgrade-impact
```

返回 simulation=true、明确说明及 impact。impact 包括五个合成用例、变化数、前后 verdict、规则差异、风险、版本／套件／报告哈希。
前端重点展示 Case E 的 before/after，不需要增加发布 UI。
此接口仅读仓库模拟补丁并复用离线分析器，不激活数据库版本、不执行在线抓取或声称法规刚刚更新。
初始化只激活真实项目默认规则，不把演示 v1/v2 补丁混作默认正式数据。

## 验证边界

初始化 → 缺签校验卡片 → 同会话补正对比 → 报告后台生成和下载链路已通过自动化集成。
SQLite 和隔离 PostgreSQL 均覆盖初始化幂等、已有活动规则／来源保护及队友业务表保留；前端组件由队友消费本页契约。

若此前用完整 SQL 快照手工建了全部表但没有迁移记录，应按数据库说明核对并登记对应迁移版本后再调用；初始化接口不会盲目 stamp。
本轮最终验证为 316 项通过（含真实 PG），与同机现有数据库同步后活动版本和已有数据均保留。
