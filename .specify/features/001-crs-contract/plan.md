# Implementation Plan: CRS 自我证明表数据契约与抽取路径修订（HK/IRD）

**Branch**: `001-crs-contract` | **Date**: 2026-11-04 | **Spec**: [spec.md](./spec.md)

**Progress updated**: 2026-11-08（合并后实现核验；不修改 feature 需求及评审结论）

**Input**: Feature specification from `.specify/features/001-crs-contract/spec.md`

## Summary

主要需求：把 `CRSFormData` 的单值 `jurisdiction_code` + `tin` 改为 `tax_residencies[]` 重复组（D3），并把单路 Vision 抽取改为「确定性文本/标签抽取 + Vision」双路并行加一致性 diff（D4）。

技术路径：证据来自 `mapping-matrix.csv`（48 字段位 × 10 列）与四份 IRD 官方 PDF 的取证结果。四份 PDF 的 SHA-256 已于 2026-11-05 从 ird.gov.hk 重新下载并逐字节比对，全部一致，哈希登记在 `assets/crs-templates/README.md`。契约修订落在 `contracts/crs-form-data.schema.json`；抽取路径修订落在 ADR-004 增补；对 PM/设计所有文档的修订以本文件 §变更单 交付（第 1–14 项仍未落笔），已发生的权属越界经设计侧复核接受，见 §Complexity Tracking V2。

关键定位修正：`assets/crs-templates/API_INTEGRATION.md:168-170` 已由规则引擎作者自行承认了多税收居民地、实体分类、控权人、邮寄地址、出生地、授权签署人、实体成立日期这七类边界。因此本轮的增量是**量化、可回溯化与给出修订方案**，不是发现。

## Technical Context

**Language/Version**: Python 3.11+（ADR-001）

**Primary Dependencies**: FastAPI、async SQLAlchemy 2.0、Alembic、uv。Vision 侧为阿里云神机百炼 Qwen-VL-Max（ADR-004 / ADR-007，SDK 或 HTTP 待 ADR-007 裁定）。确定性抽取侧需新增 PDF 解析依赖 —— 2026-11-05 团队已批准，见 §Complexity Tracking V1。

**Storage**: 开发 SQLite，生产阿里云 PG 16（ADR-008）；上游 ADR-003 已选择 JSON 文件，本 fork 规则版本存储采用 DB，按用户确认，本轮先核对黑盒 API 流程，内部存储不作为迁移阻塞。

**Testing**: 本 feature 规划阶段未新增实现测试；fork 规则引擎已补充自动化测试，当前结果见 §实现现状。

**Target Platform**: Linux 服务器（阿里云 ECS，ADR-006）

**Project Type**: Web 服务（`backend/` + 规划中的 `frontend/`）；规则引擎为同仓内部服务（用户已确认），边界见 `API_INTEGRATION.md:4`「本接口不负责读取 PDF、OCR、调用大模型提取信息」。

**Performance Goals**: 承接 PRD §2.2 —— 端到端 ≤30s、字段抽取准确率 ≥90%、TIN 校验 100%、裁决 100%、规则热加载 ≤3s。其中 ≥90% 一项当前**无产生机制**：PRD 原定的度量方式是 5 个 Case 对人工标注真值，样本量不足以持续度量。D4 的字段级一致率（spec.md SC-004）补的是**运行时代理裁判，不是准确率本身**——两路读取同一份文档，文档歧义时会相关失败、可以一致地同错，故一致率不构成准确率的下界。二者在 PRD §2.2 与 §7.1 中并列为两行（2026-11-05 PM 裁定，见 §变更单第 24 项）。

**Constraints**: ADR-010 固定 `pool_size=3, max_overflow=0`，不得上调。AGENTS.md 禁止硬编码 CRS 规则、禁止新增未经团队同意的顶层依赖、禁止拆仓。已发布接口对未知字段零容忍（`API_INTEGRATION.md:97`）且请求体上限 1 MiB（`:158`）。

**Scale/Scope**: 竞赛演示量级。本轮范围为 HK 单法域、48 个字段位、24 条严重缺口的处置。

**实现现状（本计划为全项目进度的唯一权威落点；更新于 2026-11-08）**

本节基于 fork 合并上游 `75fb627` 后的实际代码核验（合并提交 `258be94`）。
此前主线检查中“规则引擎及相关目录不存在”的结论已被 fork 实现覆盖，不再作为当前进度依据。
新契约字段及可确定性规则已接入现有 API（cee314f 及后续修正）；双路抽取及依赖外部事实的要求仍待实现，不能认定本 feature 已完整验收。

| 能力 | 当前状态 | 代码与证据 |
| --- | --- | --- |
| 工程底座 | 已实现 | 应用工厂、配置、日志、异常、健康探针、异步 SQLAlchemy、Alembic、Docker |
| 规则持久化 | 已实现，SQLite／本地 PG 已验证 | `backend/models/rule_*.py`、`backend/repositories/rules.py`；六张基础表、两张历史表、两张异步任务表与一张 PDF 报告表，已有迁移脚本 |
| TIN 规则与算法 | 已实现，有明确覆盖范围 | `rules/rules_global_v4.json`：22 法域、66 选择器；格式与校验位区分，未覆盖转人工；不是完整税法覆盖 |
| 完备性与裁决 | 已实现 | 日期、签名声明、TIN／豁免一致性；BLOCKER 优先的三态裁决 |
| 异步校验 API | 已实现、自动化验证 | `POST /api/v1/rule-engine/tasks` + `GET /api/v1/rule-engine/tasks/{task_id}`；同步 validate 隐藏并保留；个人／实体／控权人新结构、单／多税籍旧格式兼容、逐项结果、问题来源、范围和执行指纹 |
| 实体日期 | 已实现 | 实体不再强制补造成立日期；个人出生日期、可选实体成立日期各自检查 |
| 发布与热加载 | 已实现 | 候选注册、显式批准、回归门禁、CAS 激活、发布历史、固定旧快照与新调用热加载 |
| 升级影响分析 | 已实现 | 离线比较、裁决／覆盖／验证深度变化、资料与执行差异、报告哈希；不调用 AI 或 DB |
| 后台规则更新 | 已实现，模拟联调通过 | 来源检查→上游结构化包→回归／影响／证据门禁→可信策略→CAS 发布；文件锁、原子报告和 cron 模板 |
| 百炼补正 Agent | 已实现，真实调用待联调 | 默认 qwen-plus；只读工具、证据引用、降级、有限重试与调用统计；未填有效 Key，未验收真实模型质量／耗时 |
| 内部历史归档／重放 | 已实现，有边界 | 单税籍 Python 服务；旧同步 HTTP 不强制归档；异步任务加密保存完整结果，不替代主 AuditSession 或完整历史重放 |
| 官方模板与测试数据 | 已提交 | 4 份 IRD PDF、个人／实体／多税籍 JSON、Case A–E 和商户 mock 数据 |
| PDF 自动生成与下载 | 本轮已完成 | 成功结果与报告待办同事务提交；后台生成、PG 加密保存、生成中重试、READY 下载及故障恢复；三条 API 分工已验证 |
| 本地数据库同步 | 已完成并复核 | localhost:5432/devdb，schema crosstax，版本 20261108_pdf_reports；11 表与 ORM 无差异，已有数据保留 |
| 测试与类型检查 | 已验证 | 合并后锁定依赖下 294 passed（含本地 PG，无跳过）；Ruff 与全量 backend Mypy 通过 |

**尚未完成或未验收**：

- `frontend/` 未创建；上传、WebSocket、主审核流水线、跨源研判、主 AuditSession/Merchant ORM、完整主审核会话的 HTML/PDF 审计报告尚未实现；规则阶段 PDF 自动生成和下载已完成。
- 双路 PDF／Vision 抽取、一致性汇总、多持有人检测、实体分类和控权人规则仍待实现；现有补正 Agent 不承担这些功能。
- 新 schema 的字段结构已由运行接口承接；阈值所需的实体形式／持股事实、机构表头和实际跨文档证据仍有输入缺口。新结构税籍行数由 1 MiB 约束，不再受 20 行上限限制；旧格式保留原上限。
- 监管参数尚未全部声明式化；现有完备性部分仍在 Python 中，不得把 66 个 TIN 选择器等同于 27 个监管参数已经实现。
- 当前用户要求的 DB 版本存储／受控来源检查，与上游 ADR-003 的 JSON 文件规则载体仍有架构差异，尚未形成团队统一裁定；本次仅更新事实，不改 ADR。
- 四项 PostgreSQL 集成用例已在本地隔离 schema 验证；云数据库、真实百炼 API、官网任务及前后端完整链路均未验收。
- cron 仅提供模板，未安装；未执行真实规则发布。资料导入 manifest 当前仅 CN/HK/SG OECD 来源，资料提取及结构化包由上游提供。
- 未出具覆盖率 ≥80% 报告，未验证端到端 ≤30s、真实抽取准确率或字段一致率指标。
- 本地合并已完成；GitHub 推送因 HTTPS 凭据缺失失败，尚不能标记远程同步完成。

需求质量清单仍归评审人所有，本次不改变其勾选状态；进度完成不等于需求或合规验收通过。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

零安装路径下 `.specify/memory/constitution.md` 不存在（已确认 ABSENT），改以 `AGENTS.md` Guardrails 与 `specs/adr/` 作为事实上的 constitution。

| 门禁 | 来源 | 判定 |
|---|---|---|
| 不得修改 `specs/` `design/` `docs/`（PM/设计所有） | AGENTS.md | **PASS（V2 已消解）** — 原判定为「PASS（有条件）：以 §变更单 交付 PM 裁决，本计划不落笔」。2026-11-05 用户指令调用 pm skill 后该前提失效：实际修改了 `specs/prd.md`（PM 所有，权属内）与 `design/ui-spec.md`、`design/architecture.md`（设计侧所有，PM 角色越权代执行），登记为 V2。同日设计侧复核确认接受这三处改动，未触发回滚。变更单第 1–14 项仍未落笔 |
| 不得硬编码 CRS 规则，规则一律来自外部配置 | AGENTS.md | **PASS** — FR-041 把 27 个监管参数全部推向外部配置；§规则表达力 证明现有 §3 结构只能承载 3 个 |
| 不得引入未经团队同意的顶层依赖 | AGENTS.md | **PASS（V1 已消解）** — 2026-11-05 团队批准新增 PDF 解析顶层依赖。本轮**未改动 `pyproject.toml`**：D4 尚无消费方代码，此刻加依赖会留下半成品，应与消费它的代码同时落地 |
| 不得拆分为多仓 | AGENTS.md | **PASS** — 规则引擎同仓（用户已确认） |
| 连接池上限不得上调 | ADR-010 | **PASS** — 本计划不涉及连接池 |
| 无未消解的 NEEDS CLARIFICATION | commands/plan.md Key rules | **PASS** — clarify 后归零（5 题，见 spec.md ## Clarifications） |
| 删除文件不得在他人所有的文档中留下断链 | 「一个事实一个权威落点」+ AGENTS.md 权属边界 | **PASS** — 5 处断链全部归零。最后一处 `AGENTS.md:95` 已于 2026-11-05 经团队确认后修复，见 §变更单第 21 项 |

**Phase 1 设计后复检**：7 项门禁全部 PASS。V1（PDF 解析顶层依赖）经团队批准消解，V2（以 PM 角色修改 `design/`）经设计侧复核接受消解，断链门禁归零。

## Project Structure

### Documentation (this feature)

```text
.specify/features/001-crs-contract/
├── spec.md                        # WHAT/WHY：46 FR + 10 SC，矩阵 48/48 行可回溯
├── mapping-matrix.csv             # 证据基线：48 字段位 × 10 列，0 空格
├── plan.md                        # 本文件：HOW + ADR 增补 + M/N 测算 + 处置清单 + 变更单 + 全项目待办
├── checklists/requirements.md     # 需求质量清单：28 项，全未勾选（评审人所有）
└── contracts/
    └── crs-form-data.schema.json  # D3 修订后的机器可消费契约
```

**范围注记**：本文件同时承担两个尺度——feature 级实施计划（§Summary 至 §变更单）与项目级进度台账（§实现现状、§项目级待办）。后者与 `001-crs-contract` 无逻辑关联，属用户明确裁决的落点选择，代价见 §对官方 plan 工作流的偏离 末条。

### Source Code (repository root)

以下为本 feature 的目标结构，非当前目录清单；当前实际实现以 §实现现状 为准。新增确定性抽取与汇总模块仍待开发：

```text
backend/agents/                    # (规划中，architecture.md:560-567)
├── media_preprocessor.py          # 既有规划 → 收窄为「共享层」：仅解密 + 页面枚举
├── deterministic_extractor.py     # 新增：确定性路（文本层 + Tagged PDF 结构树）
├── vision_parser.py               # 既有规划 → Vision 路
├── extraction_aggregator.py       # 新增：一致性 diff + 字段级一致率
├── form_checker.py                # 既有规划 → FR-006..FR-012 / FR-021..FR-027 完备性
├── tin_validator.py               # 既有规划 → FR-018 派生等值（R32，algorithm=HKID_WEIGHT）
├── indicia_reasoner.py            # 既有规划 → FR-016 跨源冲突（注册成立地双源并列）
├── verdict_resolver.py            # 既有规划 → FR-033 星号→BLOCKER 严重度映射
└── audit_trail.py                 # 既有规划

backend/engine/                    # (规划中，architecture.md:568-570)
├── rule_engine.py                 # 既有规划 → FR-041 的 27 个监管参数求值
└── models.py                      # 既有规划 → CRSFormData 落点，承接 D3 修订

rules/                             # 已有 TIN 配置；FR-041 的完整生效日／监管参数模型仍待对齐
└── hk/                            # 建议分层，见 §变更单第 9 项
```

**Structure Decision**: 单项目 `backend/` + 同仓 `rules/`。FR-036 的「独立性边界」在目录结构上可见并可静态检查：`media_preprocessor.py` 是两路唯一允许共同导入的模块；`deterministic_extractor.py` 与 `vision_parser.py` 之间 MUST NOT 相互导入；`extraction_aggregator.py` 导入两者。任何违反上述导入图的变更即违反 FR-036，可由导入图检查自动捕获，无需人工评审。

## 项目级待办

**状态列按 2026-11-08 合并后的 fork 实现核验；本 feature 专属工作仍按其独立验收标准跟进。**

状态标记：**待办** = 尚未开始｜**本 feature 已完成** = 由 001-crs-contract 交付｜**部分完成** = 本 feature 覆盖一部分｜**已过期** = 事实已存在而原状态错误｜**已并入** = 内容见他处，此处只留指针

### 需求阶段

| 条目 | 状态 | 落点 / 依据 |
|---|---|---|
| 明确 MVP 交付范围 —— 竞赛必演示 vs 加分项 | 待办 | — |
| 定义目标用户角色（商户 / 合规官 / 系统管理员）及核心场景 | 待办 | — |
| 编写用户故事，覆盖五步流水线每条主路径 | 部分完成 | 本 feature spec.md 已产出 5 个用户故事（P1–P5），但只覆盖 HK 表单受理与抽取，未覆盖五步流水线全程 |
| 定义验收标准，每个故事附可测试通过条件 | 部分完成 | 本 feature SC-001–SC-012 为可复算判据；其余流程待补 |
| 确认首批覆盖法域列表（CN/HK/SG）及各国 TIN 规则来源 | 部分完成 | 本 feature 只处理 HK，并已证明 CN/SG 未配置时须走 `MANUAL_TRIAGE` 兜底（FR-042）；法域清单本身待裁定 |
| 定义 CRS 自证表单的完整字段清单与数据格式 | **本 feature 已完成** | `mapping-matrix.csv` 48 字段位 + `contracts/crs-form-data.schema.json` 62 字段位 |
| 定义 Mock 商户底表数据结构 | 待办 | `specs/data-spec.md` §2 已有雏形；`assets/mock-data/` 仅 `.gitkeep` |
| 确定 5 个典型 Case 测试场景（覆盖三态） | 待办 | ADR-005 |
| 明确 Reason A/B/C 豁免逻辑树的完整规则 | **部分完成** | 本 feature §规则表达力测算 已量化 3 个参数（枚举 A/B/C、理由 B 最小长度、理由 C 适用前提）并判定现有 §3 结构 M=0；FR-015/FR-020 已定互斥关系与「适用性不自动判定」；完整逻辑树待规则配置落地 |
| 定义性能指标：端到端响应时间目标 | **已过期** | `specs/prd.md:57-61` 早有 5 条量化值（≤30 秒 / ≥90% / 100% / 100% / 100%） |
| 定义安全需求：传输加密 / 存储加密 / RBAC / 数据最小化 | 部分完成 | FR-046 已扩展加密字段清单，clarify Q4 已定留存收窄策略；传输加密与 RBAC 待办 |
| 定义审计合规需求：不可篡改 / 规则版本绑定 / 全链路溯源 | 待办 | 架构文档 §2.2.1 |

### 设计阶段

| 条目 | 状态 | 落点 / 依据 |
|---|---|---|
| 前后端接口契约定义（OpenAPI 3.0）→ `design/openapi.yaml` | 待办 | 本 feature 产出的是 JSON Schema 2020-12；两者关系已于 2026-11-05 裁定为 `$ref` 外链，见 §变更单第 20 项 |
| 审计报告模板设计（Jinja2 → HTML/PDF，字段与布局） | 待办 | `assets/templates/` 仅 `.gitkeep` |

### 实现阶段

| 条目 | 状态 | 落点 / 依据 |
|---|---|---|
| 前端工程初始化（Vite + React 18 + TS + Ant Design + ESLint/Prettier） | 待办 | `frontend/` 整目录不存在 |
| SQLAlchemy ORM 模型（AuditSession / Merchant） | 待办 | `base.py`/`user.py`/`repositories/base.py` 已就绪；**`CRSFormData` 有两个候选落点，见 §变更单第 19 项** |
| Mock：商户底表 `mock_merchants.json` | 已实现（合成数据） | `assets/mock-data/mock_merchants.json`；不是实际 KYC 接入 |
| Mock：5 个 CRS 样本表单（PDF / 图片） | 部分完成 | `assets/crs-templates/` 已有 4 份 IRD 官方 PDF（个人 / 实体 / 控权人 / 术语），可直接作 HK 样本；仍缺 CN/SG 样本、扫描件与图片件 |
| 规则配置 `rules/rules_v1_base.json`（CN/HK）及全球目录 | 部分完成 | 基线、补丁、全球 v4 已提交；TIN 选择器覆盖不等于 FR-041 的全部监管参数已实现 |
| 规则补丁 `rules/rules_v2_patch.json`（热重载演示） | 已实现 | 完整 CN/HK/SG 快照；Case E 与后台更新热加载测试通过 |
| OpenAPI 契约文件编写 | 部分完成 | `backend/api/openapi.json` 与运行时快照一致；仅规则校验，完整 audit/rules/cases 契约未实现 |
| Pydantic 请求/响应模型（`backend/api/schemas/`） | 部分完成 | `structured_contracts.py` / `structured_validation.py` 已承接新字段和确定性检查；跨源证据及完整 feature 验收仍待完成 |
| REST 路由 `/api/v1/audit`、`/api/v1/rules`、`/api/v1/cases` | 待办 | 当前已有任务提交／查询接口，旧同步 `/api/v1/rule-engine/validate` 隐藏保留；管理能力为内部 CLI，不增加公开路由 |
| WebSocket 端点 `/ws/audit/{session_id}` | 待办 | — |
| 媒体预处理 / Vision / TIN / 热加载 / 完备性 / 跨源研判 / 裁决 / 审计 | 部分完成 | TIN、热加载、完备性、裁决和内部归档已实现；抽取、跨源研判和主流水线待办 |
| 新增 `deterministic_extractor.py`、`extraction_aggregator.py` | **本 feature 新增** | 见 §Project Structure 与 §Phase 0 ADR-004 增补 |
| 逐行核实 `mapping-matrix.csv` 的 `path_capability` 列 | 待办 — **D4 实现期的首个待办** | 当前 43 个 `BOTH` 是默认值而非核实结论（已核实的只有 5 个 `VISION_ONLY`：R21/R22/R26/R35/R36）。核实需解密后读取字形与结构树，即 V1 依赖落地后才能做。核实前 SC-004 的一致率带有乐观偏差，方向与 SC-009 的反作弊意图相反，见 §Phase 0 ADR-004 增补 |
| 受理层多持有人检测与拒收归因 | 待办 — **本 feature 新增** | FR-005 / FR-047 / SC-012；判据为「持有人身份块出现两次」，MUST NOT 按重复组计数 |
| 审计报告生成（Jinja2 渲染 HTML/PDF） | 部分完成 | 规则阶段 PDF 已自动生成、加密保存 PG 并可下载；完整主会话 HTML／PDF 仍待主流程实现 |

### 前端 SPA（11 项全部待办）

Layout 框架（Header + Sider + Content）｜Axios 客户端 + API 模块（audit/rules/cases）｜`useAuditStream` Hook｜文件上传（react-dropzone + AntD Upload）｜样本选择与 Case 切换｜PipelineStatus（AntD Steps + WS 驱动）｜VerdictBanner（Alert，三态语义）｜RemediationCard（Collapse，字段级提示）｜ConflictEvidence（Descriptions + Progress 置信度）｜AuditTrail + 报告下载｜RuleReload 热重载演示

> **与本 feature 的三个接口点**：①RemediationCard 须能渲染 `tax_residencies[]` 的多行重复组——原单值契约下修复卡片只需一行；②RemediationCard 还须能承载 `MULTI_HOLDER_DOCUMENT` 拒收（FR-047 裁决为 `NEED_USER_FIX`，按 `specs/data-spec.md` §1.3 该裁决的定义就是「生成修复卡片」，其修复动作是「改为每位持有人各提交一份」而非改字段值，与既有卡片形态不同）；③ConflictEvidence 须能展示 clarify Q1 的注册成立地双源并列、clarify Q4 的字段级一致性标记，以及 FR-048 / SC-011 的「单路可及字段位数」计数器——该计数器与共享层失败计数器并列展示，缺一即无法复算 SC-004 的分母。

### 测试

| 条目 | 状态 |
|---|---|
| 后端各模块单元测试（TIN 校验 / 冲突判定 / 裁决逻辑） | 部分完成 — TIN、裁决、来源、发布、Agent 等已有测试；真实跨源研判未实现 |
| 后端业务 API 路由测试（TestClient 覆盖 audit/rules/cases） | 部分完成 — 规则校验 HTTP 测试已实现；audit/rules/cases 待实现 |
| 前端组件单元测试（Vitest + RTL） | 待办 |
| 5 个 Case 端到端集成测试（前后端联调） | 待办 |
| 边界条件测试（未配置法域兜底、空文件、损坏 PDF） | 部分完成 — 未覆盖地区／类型、字段错误、请求及响应限额等已测试；文件受理待实现 |
| 热重载验证（加载 v2 补丁后即时生效） | 已实现 — 自动测试涵盖版本切换、旧快照隔离、下一调用读取新版本；真实部署时延未验收 |
| WebSocket 实时推送验证 | 待办 |
| 审计完整性验证（穿透溯源至原始文件 + 规则版本） | 部分完成 — 规则版本、指纹、发布历史与内部重放已测试；原始文件／主会话穿透待办 |
| 覆盖率达标（`fail_under = 80`） | 待验证 — 已有 294 项通过（含本地 PG），不以测试数量代替覆盖率报告 |

### 部署阶段（13 项全部待办）

**云基础设施**：阿里云资源规划与开通（ECS / 容器服务 / 存储 / 网络 / Redis）｜PG 16 连接验证（连接池已按 ADR-010 落地 `pool_size=3, max_overflow=0`，待内网连通性实测）｜部署流水线配置｜环境变量与配置管理（`.env.example` + pydantic-settings + `.gitignore` 已就位；`DASHSCOPE_API_KEY` 已接入，真实 Key／模型联调、`SECRET_KEY` 与访问控制仍待完成）

**安全加固**：HTTPS / TLS 传输加密｜数据存储加密（FR-046 已扩展敏感字段清单至 HKID/护照号、出生日期、出生地；实现待办）｜RBAC 角色隔离｜数据最小化与留存策略（clarify Q4 已定收窄规则；实现待办）

**竞赛演示**：Demo 环境部署与冒烟测试｜演示脚本编写（覆盖三态完整流程）｜演示数据走查（5 Case）｜热重载演示环节准备｜团队预演与排错

### 文档归档索引

| 文档 | 位置 | 说明 |
|---|---|---|
| PRD | `specs/prd.md` | 产品需求文档（PM-owned） |
| 数据模型规格 | `specs/data-spec.md` | 前后端共享数据契约（PM-owned） |
| 架构决策记录 | `specs/adr/` | 10 个独立 ADR，001–010（PM-owned） |
| 架构设计文档 | `design/architecture.md` | 分层架构、Agent 接口、部署方案（设计侧 owned） |
| 架构蓝图 | `design/diagrams/architecture-overview.html` | 四层分层架构可视化 |
| UI 设计规范 | `design/ui-spec.md` | 组件、布局、色彩、交互规范 |
| UI 原型 | `design/prototypes/react-ui-wireframe.html` | 可交互线框原型 |
| Agent 编码规范 | `AGENTS.md` | Monorepo 结构约定、编码规范、Guardrails |
| 方案原始需求 | `docs/proposal/crosstax-ai-solution (from ppt).md` | 原始 Proposal |
| 业务流程设计 | `docs/proposal/business-workflow-design.md` | 团队业务专家输出 |
| CRS 契约修订规格 | `.specify/features/001-crs-contract/spec.md` | 46 FR + 10 SC + 5 用户故事 + 5 条 clarify 决议 |
| CRS 契约修订计划 | `.specify/features/001-crs-contract/plan.md` | 本文件；含全项目进度与待办 |
| 字段位映射矩阵 | `.specify/features/001-crs-contract/mapping-matrix.csv` | 48 字段位 × 10 列证据基线 |
| 需求质量清单 | `.specify/features/001-crs-contract/checklists/requirements.md` | 28 项，全未勾选（评审人所有） |
| 修订版数据契约 | `.specify/features/001-crs-contract/contracts/crs-form-data.schema.json` | JSON Schema 2020-12，62 字段位 |
| IRD 官方样本与接口文档 | `assets/crs-templates/` | 4 份 PDF（含 SHA-256 登记）+ 2 份示例 JSON + README + API_INTEGRATION |

## Phase 0 研究：ADR-004 增补草案

以下为对 `specs/adr/004-vision-api.md` 的增补草案（≤60 行）。ADR-004 现行 `否决方案`（`:12-13`）只有「自部署 OCR 模型」一条——**确定性文本/标签抽取从未进入选项空间被评估过**，这是本增补要修补的核心缺陷。若团队遵循 ADR 不可变惯例，本草案应改为新发 ADR-011（amends ADR-004），内容不变。

```markdown
## 决策（修订）
表单字段抽取采用双路并行 + 一致性 diff：
- 确定性路：读取 PDF 文本层与 Tagged PDF 结构树（/Table /TR /TD），零模型推理
- Vision 路：栅格化后调用 Qwen-VL-Max（原 ADR-004 决策，保留不变）
- 共享层严格限定于解密 + 页面枚举；两路在字段定位与文本归属逻辑上互不依赖
- 汇总层逐字段位比对，按 FR-048 三分：声明 `BOTH` 而结果不同（含一空一有值）记不一致并保留双方原值、不采信任一路；声明单路可及者不进分母、单独计数；路级运行失败按 FR-039。一致率分子分母定义见 SC-004
- 字段位可及性由 `mapping-matrix.csv` 的 `path_capability` 列静态声明，当前 43 `BOTH` / 5 `VISION_ONLY`（R21、R22、R26、R35、R36）。**这 43 个 `BOTH` 是默认值而非逐行核实结论**——核实需要解密后读取字形与结构树，即 V1 依赖落地后才能做；在核实前 SC-004 的一致率带有「默认乐观」偏差，方向是低估单路盲区、从而高估一致率，与 SC-009 的反作弊意图相反，故列为 D4 实现期的首个待办

## 否决方案（增补 4 条，原 1 条保留）
- **单路 Vision（现状）**：官方 PDF 是 Tagged PDF（/Marked true），结构树可无损给出
  表格行列归属；栅格化再用视觉模型反推布局，是主动丢弃可用信息再去猜测它。
  且无第二路 ⟹ 字段级一致率无从产生 ⟹ PRD §2.2 的 ≥90% KPI 永久不可验证。
- **单路确定性抽取**：只覆盖有文本层的 PDF。客户扫描件的图像版表单无文本层，此路
  直接失效；手写签名与勾选标记（控权人表 Part 4 的 11×3 矩阵靠勾选表达）在文本层不存在。
- **两路串行（先确定性，失败再 Vision）**：只有确定性路失败时才有第二路结果，一致率的
  分母退化为少数失败样本，失去统计意义；且延迟叠加，威胁 PRD §2.2 的 ≤30s。
- **LLM 直读全文输出 JSON（无字段位约束）**：无法产生逐字段位的一致性标记，
  FR-036 的清单无从生成；且幻觉不可检测。
- **自部署 OCR 模型**（原否决项，理由不变）：竞赛环境无 GPU，训练成本高。

## 理由（增补）
- 确定性路在官方 Tagged PDF 上接近无损，零幻觉、零 API 成本、可完全单元测试
- Vision 路覆盖扫描件、手写与勾选标记，保留原 ADR-004 的全部价值
- 双路并行产生的字段级一致率是本项目此前缺失的正确性裁判（oracle），
  把 PRD §2.2 中不可度量的 ≥90% 变为可复算指标

## 后果（增补）
- 一致率分母 MUST 排除共享层失败并单独计数（spec.md SC-009），否则指标系统性虚高
- FR-048 增设第二个独立计数器「单路可及字段位数」，与 SC-009 的共享层失败计数器互不吸收（SC-011）。两个计数器堵住的是同一种虚高的两条不同通道：一条是共享层失败被算作一致，另一条是能力边界被算作不一致后再被排除
- 多持有人文档在受理层即被拒收（FR-005 / FR-047，归因 `MULTI_HOLDER_DOCUMENT`，裁决 `NEED_USER_FIX`），不进入双路抽取，因此不影响一致率；SC-012 的反向闸保证合法重复组不触发误拒
- 不一致字段位降级人工（FR-038），人工量上升，但这是把不确定性显式化而非隐藏
- 额外成本是确定性路的实现与维护；Vision 路 API 成本不变
- ADR-007 的 SDK / HTTP 裁定不受影响
- 需新增 PDF 解析依赖；AGENTS.md 顶层依赖门禁已于 2026-11-05 获团队批准（见 plan.md §Complexity Tracking V1）。依赖与本增补的消费方代码同批落地，不单独提前引入

## 实现状态（修订）
- 尚未接入。`backend/agents/` 全部为规划中；本增补新增 2 个模块
  （deterministic_extractor.py、extraction_aggregator.py），
  并把 media_preprocessor.py 的职责收窄为共享层。
```

## Phase 1 数据模型

`spec.md §Key Entities` 已定义 10 个实体，此处只补实现落点与修订性质，不重复实体描述。

| 实体 | 落点 | 修订性质 |
|---|---|---|
| 自我证明文档 | `backend/engine/models.py` 新增 | 全新；文档层属性（加密 / 结构树可用 / 续页 / 指纹） |
| 账户持有人 | `CRSFormData` 拆分个人 / 实体分支 | **破坏性**；`holder_name` 拆为姓名组成部分（FR-006） |
| 姓名组成部分 | 同上 | 全新；R05–R09 |
| 结构化地址 | `residence_address` → 结构化 | **破坏性**；拼接字符串不可逆（R13–R17） |
| 税收居民身份 | `jurisdiction_code`+`tin` → `tax_residencies[]` | **破坏性**；D3 核心（R28–R31） |
| 实体分类 | 新增 | 全新；R21/R22，`holder_type` 不可替代（`API_INTEGRATION.md:83`） |
| 控权人关联 | 新增 | 全新；R23/R25/R26，带链接置信度（FR-045） |
| 签署声明 | 扩展 | `has_signature`/`signing_date` 保留，新增消解结果 / Capacity（R35–R39） |
| 监管参数 | `rules/hk/*` | 全新；27 个参数带 `effective_from`（FR-041） |
| 抽取证据 | `extraction_aggregator.py` 输出 | 全新；FR-036–FR-040、FR-048 |

## 规则表达力测算（M/N）

`specs/data-spec.md:129-133` 的规则配置结构为 `{jurisdiction_code}: {.regex, .algorithm}`。下表统计三份表单与术语表中可确定性求值的监管参数（N），以及该结构能表达的个数（M）。逐参数的表单出处可由 `mapping-matrix.csv` 的 `executable_check` 列复算。

| 参数类别 | N | §3 可表达 M |
|---|---|---|
| TIN 格式、校验算法、清洗（去空白/括号/连字符、转大写，见 `API_INTEGRATION.md:96`） | 3 | 3 |
| 控权人门槛：法团 25% / 合伙 0% / 生效日 2021-01-01 | 3 | 0 |
| 罚则级别、罚则金额 $10,000、变更通知期限 30 天 | 3 | 0 |
| 无 TIN 理由枚举 A/B/C、理由 B 最小长度、理由 C 适用前提 | 3 | 0 |
| 跨字段派生等值：个人 TIN=HKID、实体 TIN=商业登记号 | 2 | 0 |
| 实体三分类判据、Passive NFE⟹控权人、无自然人控制⟹高管兜底 | 3 | 0 |
| 星号→BLOCKER 严重度映射、「Not compulsory」清单、「not applicable」合法空值 | 3 | 0 |
| 基数约束：一文档一持有人、控权人回指 1..3、税收居民地 ≥1 | 3 | 0 |
| 签署日期 ≤ policy.today、dd/mm/yyyy→ISO、地址国家码 ISO、链接置信度阈值 | 4 | 0 |
| **合计** | **27** | **3** |

**M/N = 3/27 ≈ 11.1%**。结论：现有 §3 结构不是「不够严」，而是**表达力维度缺失**——它只有法域一个维度，而 27 个参数中至少需要「实体形式」「生效日期」「字段位」「文档类型」四个额外维度。§3 的 `.algorithm` 枚举已含 `HKID_WEIGHT`，说明作者已预见到跨字段等值的需求，但结构上没有承载它的位置。

## 24 条严重缺口处置清单（FR-034 / SC-003）

处置类别：**IN** = 纳入数据契约（含文档层属性）｜**RULE** = 只纳入规则配置，不产生契约字段｜**PART** = 部分纳入（规则纳入而槽位全展开排除）｜**OUT** = 显式排除转人工。

| 处置 | 数量 | row_id |
|---|---|---|
| IN | 19 | R04 R06 R07 R10 R11 R12 R14 R16 R21 R25 R26 R28 R29 R33 R35 R38 R39 R47 R48 |
| RULE | 3 | R27 R32 R41 |
| PART | 2 | R22（子项填空纳入；Word Textbox 归属在线性抽取下会丢失，记为已知抽取限制）<br>R23（Passive NFE⟹≥1 的条件必填规则纳入；8 个槽位全展开排除，遵循 brief） |
| OUT | 0 | — |

R10 / R12 的**字段位**归 IN（FR-019 要求分别保留 HKID 与商业登记号），其**等值规则**归 R32 的 RULE。此区分是本清单唯一的双重处置点，也是先前一版把分布误算为 17/5/2/0 的原因。

处置结果 MUST 通过既有接口的 `verification_level` 与「已执行 / 未执行检查」字段披露（`API_INTEGRATION.md:131,136`），不新造披露格式。现有 `FORMAT_ONLY` 取值即为「只查了格式」的诚实标记，PART 与 RULE 类处置应沿用同一模式扩展取值。

## 变更单（交付 PM 裁决，本计划不落笔）

| # | file:line | 现状 | 改为 | 依据 | 权属 |
|---|---|---|---|---|---|
| 1 | `specs/prd.md:171` | 边界：「不支持加密 PDF」 | 「支持空用户密码加密的 PDF（IRD 官方样本即为 AES-128 /V4 /R4 /CFM AESV2）；无法解密或损坏时给出与『加密』可区分的归因并转人工」 | R47；SC-001 当前为 4/4 拒收 | PM |
| 2 | `specs/prd.md:169` | 处理：「PDF → pdf2image 栅格化（300 DPI RGB）」 | 「PDF → 共享层（解密 + 页面枚举）后分两路：① 确定性路读文本层与 Tagged PDF 结构树；② Vision 路栅格化 300 DPI。图片仅走 Vision 路」 | R48（/Marked true，含 /Table /TR /TD） | PM |
| 3 | `specs/prd.md:178-180` | F2「Vision Parser Agent」 | 更名「双路抽取与一致性汇总」；输出字段改为指向 `contracts/crs-form-data.schema.json`；置信度行补「两路不一致字段位不采信任一路」 | FR-036–FR-040、FR-048 | PM |
| 4 | `specs/prd.md:288` | 存储加密：「敏感字段（TIN、商户信息）」 | 增列 HK 身份证号 / 护照号、出生日期、出生地 | FR-046 | PM |
| 5 | `specs/data-spec.md:15-24` | §1.1 列 10 个字段 | 与实际接口的 13 字段对齐（补 `holder_type`、`tin_type`），并以 `tax_residencies[]` 替换 `jurisdiction_code` + `tin` | `API_INTEGRATION.md:77-92`；D3 | PM |
| 6 | `specs/data-spec.md:16` | `holder_dob` 必填，说明「出生日期 / 成立日」 | 拆为 `birth_date`（个人/控权人，必填）与 `incorporation_date`（实体，条件必填且**当前无表单来源**） | 实体版 PDF Part 1 逐字段核对无成立日；`assets/crs-templates/README.md` 与 `API_INTEGRATION.md:80,170` 已承认 | PM |
| 7 | `specs/data-spec.md:29-38` | JSON 示例用实体 `ACME Trading Ltd` 却填 `holder_dob` | 改为个人版示例，或为实体示例显式标注该值来源为上游补充 | 第 6 项缺陷在文档中的自我实例化 | PM |
| 8 | `specs/data-spec.md:11`（§1.1 标题） | 「CRSFormData — Vision Agent 抽取的结构化输出」 | 改为「双路抽取汇总后的结构化输出」 | FR-036；标题绑定单路会阻碍 D4 | PM |
| 9 | `specs/data-spec.md:129-133` | §3 结构 `{法域: {正则, 算法}}` | 扩展为分层结构，增加「实体形式」「生效日期」「字段位」「文档类型」四个维度；`.algorithm` 枚举保留（含 `HKID_WEIGHT`） | M/N = 3/27 ≈ 11.1% | PM |
| 10 | `specs/data-spec.md:135` | 数据来源：`rules/rules_v1_base.json`、`rules/rules_v2_patch.json` | 两文件均不存在（`rules/` 为空目录）。要么补齐，要么改为实际路径。**并须与 `API_INTEGRATION.md:134` 的「当前 global v4 规则」对齐命名**——global v4 与 v1_base / v2_patch 是两套互不认得的规则集命名，都声称描述同一份活动规则；载体已按第 25 项裁定为 JSON 文件，故命名以 `rules/` 下的实际文件为准，`global v4` 需规则引擎作者说明它对应哪个文件或哪组文件的组合 | 文档-代码冲突 | PM |
| 11 | `specs/adr/004-vision-api.md:12-13` | 否决方案仅「自部署 OCR 模型」1 条 | 见 §Phase 0 研究 增补草案（补入 4 条，共 5 条） | 确定性抽取从未被评估 | PM |
| 12 | `design/architecture.md:23` | 「确定性 + 智能混合：TIN 校验等规则层为确定性计算，跨源冲突研判引入 LLM 推理」 | 增补一句：此处「确定性」指规则层与 LLM 推理的分工，与 ADR-004 增补中「确定性抽取路径」不是同一概念，不可互相引用 | spec.md ## Clarifications Q2 | PM |
| 13 | `design/architecture.md:128-129` | 组件表两行 MediaPreprocessor / VisionParserAgent | 拆为四行：MediaPreprocessor（收窄为共享层）/ DeterministicExtractor / VisionParserAgent / ExtractionAggregator | FR-036 | PM |
| 14 | `design/architecture.md:560-570` | `backend/agents/` 规划树 7 个模块 | 增列 `deterministic_extractor.py` 与 `extraction_aggregator.py` | §Project Structure | PM |
| 15 | `assets/crs-templates/README.md` 文件表 | 只列 2 份官方文件 | 补列 `crs-controlling-person-ird.pdf` 与 `crs-terms-ird.pdf`，并记录四者 SHA-256 | 实体版 Part 3 明文要求 Passive NFE 另附控权人表 | **已执行 2026-11-05（用户授权）** — 表格补至 4 行；SHA-256 另立一张表，四份哈希均于同日从 ird.gov.hk 重新下载比对一致（terms 版真实地址为 `terms.pdf`，`scf_terms.pdf` 返回 404） |
| 16 | `assets/crs-templates/README.md` 表格能力段 vs 接口边界段 | 一处称「两份表格均支持多个税收居民地区」，另一处称「当前接口一次只支持一个」 | 保留矛盾但显式标注为已知差距并指向本 feature；D3 落地后删除后者 | 内部自相矛盾 | **已执行 2026-11-05（用户授权）** — 两处互相指认，并声明「表格支持 ≠ 接口支持」。因 D3 尚无实现，接口侧那行**未删除**，标注为落地前仍然成立 |
| 17 | `assets/crs-templates/README.md`、`API_INTEGRATION.md:98` | 链接 `../../backend/api/RULE_ENGINE_API.md` | 该文件不存在（已验证）。改指实际路径或删除链接 | 断链 | **已执行 2026-11-05（用户授权）** — 未指向 `backend/engine/rule_engine.py`（那是实现文件而非接口文档，且尚不存在），改指 `API_INTEGRATION.md` 与服务运行后由代码生成的 `http://localhost:8000/docs`，后者不会与实现漂移 |
| 18 | `API_INTEGRATION.md:168-170` | 「当前接入边界」三条 | D3 落地后第 168 行须删除；169/170 须按处置清单更新 | FR-034 | **部分执行 2026-11-05** — D3 尚无实现，三条边界对**已发布契约**仍然全部为真；删除或改写任何一条都会让文档描述一个不存在的能力。故只在该节末尾追加一段：声明四项已完成契约层设计但尚无实现，落地前本节每一条仍然成立，不得据设计文档提前提交新字段 |
| 19 | `design/architecture.md:545` vs `:570` | `:545` 规划 `api/schemas/` 为「Pydantic 请求/响应模型」，`:570` 规划 `engine/models.py` 为「CRSFormData / AuditIssue 等」——`CRSFormData` 有两个落点 | 裁定唯一权威落点，另一处只做导入转发 | D3 的 `tax_residencies[]` 若需在两处各改一次，必然漂移；违反「一个事实一个权威落点」 | PM |
| 20 | §项目级待办 设计阶段 | 规划产出 `design/openapi.yaml`（OpenAPI 3.0，前后端接口契约），文件至今不存在 | 裁定它与 `contracts/crs-form-data.schema.json`（JSON Schema 2020-12）的关系：①`CRSFormData` 只在 JSON Schema 中定义，`openapi.yaml` 以 `$ref` 外链引用；或 ②两份各自独立、接受漂移 | 两者都声称是「结构化契约」的权威落点。OpenAPI 3.0 内嵌的 Schema Object 是 JSON Schema 的受限子集（不支持 `$defs` 全量语义），若各写一份，D3 的 `tax_residencies[]` 必然只改到一处 | **已裁定 2026-11-05（PM 角色）**：选 ①。`CRSFormData` 只在 `contracts/crs-form-data.schema.json` 中定义，`openapi.yaml` 产出时以 `$ref` 外链引用。已落入 `design/ui-spec.md:503` |
| 21 | `AGENTS.md:95` | 「Scaffold it first (ROADMAP §3.1)」 | 改指本文件 §项目级待办 实现阶段，或直接删除该括注 | 指向已删除文件的入站引用，仓库内仅此一处。AGENTS.md 不在保护目录内，但它是本项目事实上的 constitution（`.specify/memory/constitution.md` ABSENT），改动建议经团队确认 | **已执行 2026-11-05（团队确认）** — 改为 `(see §项目级待办 实现阶段 in \`.specify/features/001-crs-contract/plan.md\`)`。仓库内指向已删除文件的入站引用归零 |
| 22 | `.gitignore`「# uv」段 vs `AGENTS.md:61` vs `design/architecture.md:426` | `.gitignore` 含 `uv.lock` 一条；`AGENTS.md:61` 写「uv.lock # uv lockfile — **commit it**, never hand-edit」；Dockerfile 用 `COPY pyproject.toml uv.lock* ./`（星号使其可选） | 从 `.gitignore` 删除 `uv.lock` 一行，并把已存在的锁文件纳入版本控制 | **三方矛盾，且失败是静默的**。已核验：`uv.lock` 在磁盘上存在（417,678 字节，2026-10-26），但 `git ls-files --error-unmatch uv.lock` 返回未跟踪，`git check-ignore` 确认被 `.gitignore` 排除。后果：任何新克隆都拿不到锁文件 ⟹ `uv sync` 现场重新解析 ⟹ 构建不可复现；而 Dockerfile 的 `uv.lock*` 通配符会静默容忍其缺失，镜像照样构建成功，只是依赖未锁定——**没有任何环节会报错**。AGENTS.md:61 表述的是正确意图，缺陷在 `.gitignore` | **已执行 2026-11-05（用户授权，含推送远端）** — 提交 `e489a83`（`.gitignore` −3 行、`uv.lock` +1858 行）已推送 `origin/master`。`AGENTS.md:61` 一字未改：改动它等于改团队约定，而根因修好后它的表述重新成立。此前临时加在 `AGENTS.md` 的 `.gitignore` 树条目上的矛盾限定说明，已随修复一并撤除 |
| 23 | `specs/prd.md` 全文（已 grep 验证：「持有人基数」「多持有人」「联名」「拒收」均无命中；`:179` 输出字段为单持有人形态） | PRD 未规定收到多持有人文档时的受理行为 | F1/F2 增补受理约束：一份文档对应一个持有人；检出第二个持有人身份块时拒收，归因码 `MULTI_HOLDER_DOCUMENT`，裁决 `NEED_USER_FIX`；并明文说明合法重复组（多税收居民地、控权人槽位 (1)–(8)、11×3 类型矩阵）**不**触发拒收 | CHK021 已裁定（FR-005 / FR-047 / SC-012）。PRD 是需求的权威落点，规格新增的受理行为若不回写，两边会各自演化；且「不触发拒收」那半句是 SC-012 反向闸的需求侧表达，缺了它实现方极易按重复组计数而误拒 D3 的核心场景 | **已执行 2026-11-05（PM 权属内）** — `specs/prd.md:182` F2 表新增「基数边界」行。**只改了 F2，未改 F1，与本项「应改为」列写的「F1/F2」不符，理由如下**：F1 的既有范围是栅格化（`specs/prd.md:170`「PDF → pdf2image 栅格化」），不读取文档内容，无法检出「持有人身份块出现两次」；FR-036 也把共享层收窄为解密 + 页面枚举。要在 F1 落这条就得扩 F1 的范围，那是新决策而非机械传播。CHK021 已裁定，此项是其向需求权威落点的传播，不含新决策 |
| 24 | `specs/prd.md:58`、`:347`、`:399` | `:58`「表单字段抽取准确率 ≥ 90%（结构化 JSON 字段级）｜5 个典型 Case 测试」；`:347`「Vision 抽取｜5 个 Case 的字段抽取准确率 ≥ 90%」；`:399`「低置信度字段自动标记为需人工复核，**不阻断流程**」 | ①`:58` 保留「准确率 ≥90%」但注明是对人工标注真值、且 5 个 Case 的样本量只够作发布门禁；**另增一行「字段级一致率」作为运行时代理指标**，分母定义指向 SC-004，并明文不得当作准确率的下界；②`:347`「Vision 抽取」措辞隐含单路，拆成「准确率（真值）」与「一致率（代理）」两行；③`:399`「不阻断流程」拆为两类处置：低置信但两路一致 → `MANUAL_TRIAGE`（WARNING，不阻断）；两路不一致 → `NEED_USER_FIX`（BLOCKER，阻断该字段位） | **同一个 KPI 现在有两套互不相同的算法**：PRD 说用 5 个 Case 测准确率，spec 说按全字段位算一致率——两套都能「达标」，但测的不是同一件事，≥90% 因此不可判定。且 `:399`「不阻断流程」与 FR-038（不一致 MUST 降级人工）+ FR-047（`NEED_USER_FIX`）直接矛盾：按 `specs/data-spec.md` §1.3，`NEED_USER_FIX` 的定义就是「存在 BLOCKER」，BLOCKER 即阻断 | **已裁定并执行 2026-11-05（PM 角色）**：选「两指标并列」。`specs/prd.md` §2.2、§7.1 各拆为准确率（真值，5 Case 作发布门禁）与一致率（代理，分母定义指向 SC-004）两行；§8.2 的 R1 应急预案拆为 WARNING / BLOCKER 两类处置。**登记一处本 Agent 的原判错误**：本项①最初写的是「指标改为指向一致率」，那会用代理指标替换掉 PRD 中唯一带真值的度量——一致率测的是两路互相 agreeing，准确率测的是对着真值 correct，两路读同一份文档可相关失败、一致地同错，故前者不构成后者的下界。§Technical Context 的 Performance Goals 此前也写着「≥90% 由一致率补上裁判」，属同一混同，已一并改正 |
| 25 | `assets/crs-templates/API_INTEGRATION.md:15`、`:161` | `:15`「需要先配置数据库并发布活动规则，否则返回 503」；`:161`「503｜RULE_ENGINE_UNAVAILABLE｜数据库或规则不可用」 | 裁定规则载体并消除冲突：维持 ADR-003（JSON 文件 + 内存原子替换，规则不经数据库），改写这两行；FR-041 的「载体 MUST 由团队裁定」回写为已裁定 | FR-041 明文要求团队裁定载体，但变更单第 1–24 项无一跟踪它——第 9 项改 `data-spec.md` §3 的结构维度、第 10 项改 §3:135 的文件路径，都不碰 API_INTEGRATION.md 的 DB 语义。一条 MUST 级裁定要求处于**无主状态**：无责任人、无落点、无截止，规则引擎开工时极可能按 DB 实现，此后回不到 ADR-003。证据权重亦悬殊：支持 JSON 文件的有 5 处独立落点（ADR-003 已采纳、AGENTS.md Guardrail、`data-spec.md` §3:135、`design/architecture.md:239`、`README.md:40`），支持 DB 的仅此 1 份零实现的契约先行文档（见 §实现现状），且该文档 `:129`「本次规则内容哈希」正是 ADR-003 理由段的实现形态，与 `:15` 自相矛盾 | **已裁定并执行 2026-11-05（PM 角色，用户确认）**：ADR-003 胜出。其否决方案「数据库存储规则：竞赛场景无需持久化查询」是**已评估并拒绝**，推翻它需要新信息，API_INTEGRATION.md 未给出任何理由。两处均为单行替换，该文件行号未平移。顺带修正 FR-041 的引用错误（原写 `:15,160`，而 `:160` 是 `NO_ACTIVE_RULES` 行、不含数据库字样，DB 措辞实在 `:15` 与 `:161`）。**遗留两项交回规则引擎作者**：①`rule_revision` 的定义（`rules_v1_base` / `rules_v2_patch` 的补丁级 1/2）是按 ADR-003 后果段推得的，非其原意；②规则引擎与主后端同仓同进程、共享 ADR-008 应用库，共享库故障是否应映射为 `RULE_ENGINE_UNAVAILABLE` 在零实现下无法断言，故本次只删除不可验证的「数据库」措辞，不新增关于共享库故障的断言 |

第 19 项是本轮新发现的冲突，此前未在任何文档中登记；第 20 项已于 2026-11-05 以 PM 角色裁定；第 15–18、21、22 项位于 `assets/` 与仓库根，不属保护目录，已于同日经用户授权与团队确认执行完毕。第 23–24 项由 CHK021 / CHK024 的裁定派生，均属 `specs/`（PM 所有），已于同日以 PM 角色裁定并执行完毕——第 24 项含一处本 Agent 原判错误的更正，见该行权属列。第 25 项裁定 FR-041 悬置的规则载体，ADR-003 胜出，同日经用户确认执行完毕，遗留两项交回规则引擎作者。变更单余下未落笔的为第 1–14 项与第 19 项。

**行号校准**：本表「现状」列引的是发现时快照。第 23–24 项执行使 `specs/prd.md` 净增 3 行，当前位置为——§2.2 准确率 `:58` / 一致率 `:59`、F2 输出字段 `:180`（第 23 项现状列写的 `:179`）/ 基数边界 `:182`、§7.1 准确率 `:349` / 一致率 `:350`（现状列写的 `:347`）、§8.2 R1 `:402`（现状列写的 `:399`）、参考文档链接 `:429`。`design/` 未改动，行号不变；`assets/crs-templates/API_INTEGRATION.md` 经第 25 项两处单行替换，行号未平移，故本表引的 `:15`、`:129`、`:134`、`:161` 均仍有效。

**断链已归零**：原 5 处（`specs/prd.md:429`、`design/ui-spec.md:503`、`design/architecture.md` 目录树与历史说明 2 处、`AGENTS.md:95`）全部修复。前三处属设计侧所有，经设计侧复核接受；最后一处经团队确认修复。

## 对官方 plan 工作流的偏离

`commands/plan.md` 的 Phase 0/1 要求产出 `research.md`、`data-model.md`、`contracts/`、`quickstart.md` 四个工件。本计划做了如下偏离，均登记于此而非静默省略：

- **`research.md` 未单独产出**：其规定格式为 Decision / Rationale / Alternatives considered，已完整内联于 §Phase 0 研究（ADR-004 增补草案含 5 条被否决方案，超过模板要求）。技术栈无未知项——ADR-001/003/004/006/007/008/010 已裁定，Technical Context 无 NEEDS CLARIFICATION，故 Phase 0 的「resolve all NEEDS CLARIFICATION」为空集。
- **`data-model.md` 未单独产出**：`spec.md §Key Entities` 已定义 10 个实体，重复一遍只会产生两处需同步维护的事实来源，违反「一个事实一个权威落点」。本文件 §Phase 1 数据模型 只补落点与修订性质。
- **`contracts/` 已产出**：`contracts/crs-form-data.schema.json`，即 D3 的机器可消费交付物。
- **`quickstart.md` 未产出**：其规定内容为「可运行的端到端验证场景 + 前置条件 + 运行命令 + 预期结果」。本轮明确不产出实现代码（用户设定的 C5 默认，未被推翻），无可运行物，写出来只能是虚构命令。SC-001–SC-012 已承担验收判据职责。
- **`tasks.md` 未产出**：由 `commands/tasks.md` 负责，不属 plan 阶段；且本轮不实现。
- **新增了模板没有的章节 §项目级待办（偏离最大的一项）**：官方 `templates/plan-template.md` 的章节集为 Summary / Technical Context / Constitution Check / Project Structure / Phase 0 / Phase 1 / Complexity Tracking，**没有任何承载项目级任务台账的位置**——spec-kit 的模型是「一个 feature 一份 plan.md」，项目级路线图不在其工件集内。本文件因此额外承载了前端脚手架、阿里云资源开通、HTTPS/TLS、竞赛演示脚本等与 CRS 数据契约无关的内容，代价是 feature plan 被项目级任务污染，且后续 `002-*` / `003-*` feature 无法复用这个落点。此为**用户明确裁决**而非本 Agent 的判断。若日后需要恢复分离，最小代价是把 §实现现状 与 §项目级待办 两节整体迁出为独立文件并重建根目录索引。

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

本轮登记 2 项，均已消解：V1 经团队批准，V2 经设计侧复核接受。两行保留作为决策历史与拒绝方案的记录，Constitution Check 已回到 7 项全 PASS。

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| **V1**：新增 PDF 解析顶层依赖（AGENTS.md 禁止未经团队同意的顶层依赖） | 确定性路必须读取 PDF 文本层与 `/StructTreeRoot` 结构树。取证已证明这是必要能力而非锦上添花：四份官方 PDF 均为 AES-128 加密，无 `cryptography` 时解析库直接抛 `DependencyError`（本轮已实际复现）；且均为 Tagged PDF，结构树是表格行列归属的唯一无损来源（R47、R48） | ①「复用现有依赖」不可行——`pyproject.toml` 无任何 PDF 解析库，PRD §4.2 提到的 pdf2image 只做栅格化，栅格化正是 R48 要停止的行为。②「只做 Vision 单路」被 ADR-004 增补草案否决：它使 SC-004 的字段级一致率无从产生，PRD §2.2 的 ≥90% KPI 永久不可验证。**2026-11-05 团队已批准，V1 消解。本轮未改动 `pyproject.toml`：D4 尚无消费方代码，此刻加依赖会留下半成品，应与消费它的代码同时落地。** |
| **V2**：以 PM 角色修改 `design/` 下 2 个文件（AGENTS.md:160 规定 `specs/` `design/` `docs/` 为 PM/designer-owned，编码 Agent 不得修改） | 用户明确指令「调用 pm skill 去更改」，目的是修复仓库中指向已删除文件的入站引用。其中 `specs/prd.md:426` 在 PM 权属内，无越权问题；但 `design/ui-spec.md:503`、`design/architecture.md:536-634`（仓库目录树）、`:636-638`（历史说明及其追加段） **归设计侧所有，PM 角色并不覆盖**。3 处改动均为机械性修复，不涉及设计决策本身：删去失效的跨文档指代、目录树与实际仓库状态对齐、历史记录后追加（原文一字未改） | ①「只改 `specs/prd.md`，`design/` 三处留给设计侧」是**更符合权属边界的方案**，代价是仓库继续带 3 处断链直到设计侧处理。未采用是因为用户指令未区分权属、且 3 处均为机械性修复。②「不改任何文件、只出变更单」已被用户在前一轮否决。③「连同 `AGENTS.md:95` 一起改」未采用：该文件是事实上的 constitution，标注为需团队确认，用户未授权。**2026-11-05 设计侧已复核并接受 `design/ui-spec.md:503`、`design/architecture.md:536-634`（仓库目录树）、`:636-638`（历史说明及其追加段）三处改动，未触发回滚，V2 消解。** |


## 2026-11-08：黑盒规则接口与新流程对齐

架构差距与职责划分见 [审查矩阵](../../../backend/engine/ARCHITECTURE_REVIEW.md)，调用方式见 [结构化接口](../../../backend/api/STRUCTURED_CRS_API.md)。
新增姓名／地址／文档／实体／控权人／声明全字段接收；香港派生等值、授权签署、ISO 代码与独立 POEM 语义检查。
表单日期规范化，表单策略独立哈希，升级影响分析支持同一新结构。
三份新的 JSON 样例通过真实 HTTP 集成测试；旧调用仍兼容，当前公开异步提交／查询两个端点。
真实双路抽取、跨文档原件对照、缺失的 KYC／持股输入和全系统加密留存不标为完成。
最新验证为 276 项通过（含本地 PG，无跳过）；Ruff 与全量 Mypy 通过，Docker 构建和真实模型未验收。


## 2026-11-08：异步规则验证交付

已完成：[详细设计](../../../backend/engine/ASYNC_TASKS.md)、[两步 API](../../../backend/api/RULE_TASKS_API.md)、三份任务样例、OpenAPI、两表迁移、认证加密及 HMAC、容量限制与幂等、冻结快照、独立 Worker、租约心跳／失租恢复、截止时间、过期清理。
提交成功才返回 202；SUCCEEDED 与业务 verdict 分开。主流程无需直查 DB，仍管理自己的会话状态与前端事件。
SQLite 真实 Alembic 命令升降级与并发队列测试通过；可选 PG 用例包含新迁移和任务 Worker 链路。
本地 PG 后续已按授权升级，云端目标仍需升级迁移、配置共享密钥并启动 API／Worker；未部署生产进程。
保留 24 小时后 GET 410；密文实际清理由运行中的 Worker 或手动 cleanup 完成，不宣称旧归档全量加密。
API 两连接加 Worker 一连接，禁止额外进程使团队连接预算超限。Docker、真实模型、云数据库与完整主流程指标仍未验收。


## 2026-11-08：数据库 SQL 与设计清理

validation_engine.sql 已更新为完整十表快照；bootstrap_rules.sql 明确承担历史六表前置基线。
任务增量 SQL 从已发布迁移生成，完整和基线 SQL 从 ORM 生成，新增 schema_sql --write/--check 与五项漂移测试。
数据库 README 替换过时六表设计、提取范围和迁移步骤；关联接口／详细设计同步指向当前部署路径。
历史迁移、内部归档及队友 User 模型保留，不删除真实表或数据。


## 2026-11-08：本地 PostgreSQL 同步验收

用户明确追加授权后连接 localhost:5432/devdb，先对八表／20261103_rule_history 做只读结构比较。
确认只缺两张任务表及三个普通索引后，通过 Alembic 应用 20261108_rule_tasks。
升级后十表与 ORM 比较无差异（含支持的类型、默认值、索引和外键项），原八表行数不变，未更改活动规则或创建测试业务数据。
全量 276 测试通过，无跳过；四项 PG 参数化生命周期在随机隔离 schema 中完成并清理。
SQL 生成一致性、Ruff 和全量 backend Mypy 通过；未生成部署密钥、未运行生产 Worker，真实模型与云端仍待验收。


## 2026-11-08：异步 PDF 报告持久化交付

先更新设计，再实现校验成功同事务建立报告待办、独立后台生成、PG 密文保存及下载只读。
API 维持三条：上游提交／查询两条，前端下载一条；查询提供 report_status/report_error，READY 有 report_url，生成中 GET 返回 REPORT_GENERATING + Retry-After: 2。
前端在校验成功后可使用固定报告路径重试，主后端不用阻塞等待报告；最终生成失败停止普通重试，内部 CLI 支持故障修复后重排 FAILED 报告。
新增 20261108_pdf_reports 迁移和增量 SQL，完整快照十一表；本地迁移已应用，原十表数据保留。
全量 294 测试通过无跳过，包含真实 PG 与独立 Worker 进程；SQL 一致性、Ruff、Mypy 和 PDF 视觉检查通过。
竞赛本轮不再开发主会话聚合与下载授权、下载审计／队列监控、OSS／KMS／真实签名，也不在本次执行阿里云部署；这些能力不标记为已实现。


## 2026-11-08：竞赛范围冻结与本地数据库复核

按用户最新要求，本轮到此收尾，以已实现规则引擎、三条 API、后台 PDF 生成和 PG 存储为交付范围；不继续扩展生产化能力。

| 工作项 | 最新状态 | 证据／说明 |
| --- | --- | --- |
| 本地迁移同步 | 已完成 | 再次执行 alembic upgrade head，数据库已为最新版本，无待执行迁移 |
| 本地结构核对 | 已完成 | 20261108_pdf_reports；crosstax 共 11 表，与 ORM 比较无差异 |
| 数据保留 | 已确认 | 来源 3、原始文档 3、同步记录 2、规则版本 4、活动状态行 1；其余相关表为空，未清空或重建数据 |
| 自动化验证 | 上阶段已通过 | 294 项通过，含真实 PG 与 Worker CLI；此次仅同步复核和文档更新，不重复运行全套测试 |
| 主会话聚合与下载授权增强 | 本轮不安排 | 属于已讨论但不继续开发的范围，不计入本轮规则引擎待办 |
| 下载审计与队列监控 | 本轮不安排 | 按竞赛时间和投入产出取舍 |
| OSS／KMS／报告签名 | 本轮不安排 | 保持当前 PG 加密存储设计 |
| 阿里云部署操作 | 本次不执行 | 保留已有部署说明，未标记为已部署 |

以上是范围取舍，不表示项目已有完整主流程／用户认证；此前的架构记录作为事实保留，不再据此自动扩展开发。
