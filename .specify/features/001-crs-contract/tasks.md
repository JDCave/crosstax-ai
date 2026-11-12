# Tasks: CRS 自我证明表数据契约与抽取路径修订（HK/IRD）

**Branch**: `001-crs-contract` | **Date**: 2026-11-12 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**Input**: `.specify/features/001-crs-contract/`（plan.md + spec.md + contracts/crs-form-data.schema.json；data-model.md / research.md / quickstart.md 不存在，偏离已登记于 plan.md §对官方 plan 工作流的偏离）

**Tests**: 包含测试任务——spec.md 每条 User Story 均带 Acceptance Scenarios，且 AGENTS.md §Testing 要求测试先行。

**Organization**: 按用户故事分组；**Phase 0 为用户明确指定的本轮优先项（2026-11-13 联调就绪三项），其余 Phase 为 feature 全量分解，非本轮承诺**。

**既有实现基线（2026-11-12 核验，勿重复劳动）**：规则引擎、异步任务三接口（提交/轮询/报告）、加密与幂等、解释卡片与补正对比、快速初始化、PDF 报告队列均已交付并冒烟通过；US2 的 `tax_residencies[]` 结构与 US3 的派生等值检查已由 `backend/engine/structured_validation.py` 承接——对应 Phase 以「验证 + 补缺」为主，不是重新实现。`backend/agents/` 现仅有 `remediation.py`；`pyproject.toml` 尚无 PDF 解析依赖（团队已批准 V1，约定与消费代码同批落地）。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行（不同文件、无未完成依赖）
- **[US1]–[US5]**: 对应 spec.md 用户故事
- 路径为仓库根相对路径

---

## Phase 0: 联调就绪（用户指定，本轮优先执行）🎯

**Goal**: 2026-11-13 前后端联调（结构化 JSON → 任务 → 轮询 → PDF）开跑前必须关闭的配置/提交/样例缺口。不涉及任何 feature 新功能。

**Independent Test**: 队友 `git clone` 后按 README → `backend/api/FRONTEND_INTEGRATION.md` 能找到入口；`.env` 的 `RULE_AI_MODEL` 为有效模型且任务响应 `result.explanation_cards` 非降级生成；第 4 份样例 JSON 实测产出 `NEED_USER_FIX`。

- [X] T001 修正 `.env` `RULE_AI_MODEL`：原值 `qwen3.7-flash` 在平台目录（`info/models.md` L29）存在，但实测 maas 专用端点返回 `Model access denied`（目录≠授权）。2026-11-12 实测本密钥可用集：`qwen-plus` / `qwen3.8-flash`（带 reasoning，不满足非思考 JSON 要求）/ `qwen3-vl-plus`（视觉，US4 预留）。已改为 **qwen-plus**（BAILIAN.md 默认值）。需同时重启 API+Worker 生效
- [X] T002 真实调用验证解释卡片：**发现并修复生产缺陷**——AI guidance 从未成功（`guidance.status=FALLBACK, reason_code=AI_INTERNAL_ERROR, attempts=0`）。根因：Windows 用户环境变量 `NO_PROXY` 含 `[::1]`/CIDR，httpx 在 `AsyncClient` 构造时按 URL pattern 解析而抛 `InvalidURL`（与 tests/conftest.py 隔离的正是此问题，但运行时无处理）。修复：`backend/agents/remediation.py` 的 provider client 加 `trust_env=False` + 回归测试 `test_host_proxy_environment_does_not_break_provider_client`。复验（新 API+Worker，qwen-plus）：**GENERATED，attempts=2，total_tokens=1634，duration 4.3s**，action 为生成文案。注意：改后端代码后必须 API 与 Worker 同步重启，否则 `TASK_BUILD_MISMATCH`（已补入 §5 排障表）
- [X] T003 新建 `NEED_USER_FIX` 样例 `assets/crs-templates/crs-individual-need-user-fix-task-request.json`：复制个人样例，将 `tin` 改为校验位错误的 HKID `A123456(9)`（与 `hk_identity` 形成双 BLOCKER），`session_id` 新 UUID、`policy.today=2026-11-12`
- [X] T004 实测 T003：202 → SUCCEEDED → **verdict=NEED_USER_FIX**（`INVALID_TIN` + `HK_TIN_IDENTITY_MISMATCH`，均 BLOCKER）→ report READY ✓
- [X] T005 更新 `backend/api/FRONTEND_INTEGRATION.md`：§3 样例表补 NEED_USER_FIX 行（三态全覆盖）+ `include_guidance` 语义说明；§3 curl 冒烟改用 Git Bash 可用的 `python -c uuid`（原 `uuidgen` 不存在）；§5 补 `TASK_BUILD_MISMATCH` 行；§6 三份→四份。启动命令统一已由并行会话完成（§1/§6 以原始命令为准，make 本机不可用）
- [ ] T006 [after-T005] 提交联调四件套：`backend/api/FRONTEND_INTEGRATION.md`、`README.md`、`specs/prd.md`（v1.3）、`.specify/features/001-crs-contract/checklists/requirements.md`，加新样例文件 `assets/crs-templates/crs-individual-need-user-fix-task-request.json`；排除 `crosstax.db.bak-20261111`、`integration_smoke_report.pdf`（后者若作联调证据则移入 `assets/` 再提交，否则补入 `.gitignore`）；尝试推送 origin（历史 HTTPS 凭据失败，失败则如实报告不重试轰炸）

**Checkpoint**: 联调就绪。⚠️ 以下 Phase 1+ 为 feature 全量工作（双路抽取等），非 11-13 联调前置，是否开工需用户另行决定。

---

## Phase 1: Setup（共享基础设施）

- [ ] T007 在 `pyproject.toml` 新增 PDF 解析依赖（能读 AES-128 空用户密码 + /StructTreeRoot，候选 pikepdf；同步 `uv.lock`，遵守 AGENTS.md「commit uv.lock」）——与 T008/T012 消费代码同批落地
- [ ] T008 [P] 建立 `rules/hk/` 目录与分层加载约定文档头（`backend/engine/rule_loader.py` 增加法域分层读取，为 T025/T028/T030 的监管参数落点）

**Checkpoint**: 依赖与规则落点就绪

---

## Phase 2: Foundational（阻塞前置）

**⚠️ CRITICAL**: US1/US4 的故事工作不能先于此 Phase。

- [ ] T009 实现共享层 `backend/agents/media_preprocessor.py`：解密（空用户密码，拒绝越权绕过）+ 页面枚举 + 指纹（`document.fingerprint`）+ `is_encrypted` / `structure_tree_available` / `has_continuation_sheets` 判定（FR-001/002/003/004；契约 `contracts/crs-form-data.schema.json#/$defs/Document`）
- [ ] T010 共享层测试 `tests/backend/test_media_preprocessor.py`：四份官方 PDF（`assets/crs-templates/*-ird.pdf`）零拒收（SC-001 4/4）、权限位受限不构成拒收（US1-AS3）、损坏/密码错误给出可区分归因非「加密」（US1-AS4）
- [ ] T011 逐行核实 `mapping-matrix.csv` 的 `path_capability` 列：用 T009 产物读取字形与结构树，把 43 个默认 `BOTH` 改为核实结论（plan.md §D4 实现期首个待办；核实前 SC-004 分母不可信）

**Checkpoint**: 入口受理可用，一致率分母诚实

---

## Phase 3: User Story 1 - 受理官方加密表单而不拒收（Priority: P1）

**Goal**: 官方 AES-128 加密 Tagged PDF 从入口 100% 拒收变为全受理并产出裁决。

**Independent Test**: 单独投放四份官方 PDF，断言零拒收、每份产出裁决对象（spec.md §US1）。

### Tests for User Story 1

- [ ] T012 [P] [US1] 确定性抽取契约测试 `tests/backend/test_deterministic_extractor.py`：Tagged PDF 结构树（/Table /TR /TD）字段-行列归属无跨行串位（US1-AS2）；「regularly traded on ___」子项填空归属正确（US5-AS3 同源能力）

### Implementation for User Story 1

- [ ] T013 [US1] 实现 `backend/agents/deterministic_extractor.py`：文本层 + 结构树抽取，输出对齐 `contracts/crs-form-data.schema.json`（零模型推理）
- [ ] T014 [US1] 受理层多持有人检测：基于持有人身份块出现两次判定（MUST NOT 按重复组计数），拒收归因 `MULTI_HOLDER_DOCUMENT`，裁决 `NEED_USER_FIX`（FR-005/047、SC-012）in `backend/agents/media_preprocessor.py` 之后的受理服务 `backend/services/document_intake.py`
- [ ] T015 [US1] [P] 受理层测试 `tests/backend/test_multi_holder.py`：拒收分支 + SC-012 反向闸（多税收居民地/控权人槽位/11×3 矩阵的合法重复组不误拒）
- [ ] T016 [US1] 文档受理端点 `backend/api/routes/audit.py`：`POST /api/v1/audit/documents`（上传加密 PDF → 受理/拒收归因 + 抽取产物），错误响应遵循 `{code,message}` 约定；在 `backend/main.py` 注册

**Checkpoint**: US1 独立可验——四份官方 PDF 投放即出裁决

---

## Phase 4: User Story 2 - 一位持有人有多个税收居民身份（Priority: P2）

**Goal**: `tax_residencies[]` 重复组任意条数、逐条独立裁决。结构与新契约**已由运行接口承接**（plan.md §实现现状），本 Phase 为按 spec 场景验证补缺。

**Independent Test**: 构造 3 居民地（1 个无 TIN 理由 B 附解释）数据直投现有接口，断言三条全留存、逐条各自裁决、无 TIN 条不因缺 TIN 判 BLOCKER。

- [ ] T017 [P] [US2] 场景测试 `tests/backend/test_tax_residencies_us2.py`：US2-AS1 三法域全保留 / AS2 六法域不截断（1 MiB 内）/ AS3 理由 B 解释去空白达最小长度且 A/C 不强制解释 / AS4 TIN 与理由共存报互斥冲突（FR-015）
- [ ] T018 [US2] 修复 T017 暴露的缺口于 `backend/engine/structured_validation.py`；理由 B 最小长度阈值从 Python 常量迁入 `rules/hk/` 配置（FR-041 增量，禁止硬编码）

**Checkpoint**: US2 全部 AS 绿

---

## Phase 5: User Story 3 - 派生等值规则自动执行（Priority: P3）

**Goal**: HKID=TIN、商业登记号=TIN 跨字段等值作为独立校验执行（现状：已接入 `structured_validation.py`，本 Phase 按 AS 验证补缺）。

**Independent Test**: 提交 HKID 与 TIN 表 HK 行故意不一致的个人版结构化输入，断言报出等值违规并指出两个来源字段位。

- [ ] T019 [P] [US3] 测试 `tests/backend/test_derived_equivalence_us3.py`：US3-AS1 个人 / AS2 实体等值违规可报且引用双字段位（R32，`algorithm=HKID_WEIGHT`）/ AS3 居民地与 POEM 语义区分不替代（FR-017）/ AS4 理由 C 适用前提显式标记 `reason_c_applicability_unverified` 而非沉默（FR-020）
- [ ] T020 [US3] 修复缺口：星号字段位 → BLOCKER 严重度映射（FR-033、SC-002 的 8 个 asterisk 行）in `backend/engine/verdict.py`；「Not compulsory / not applicable」空值不判缺失（R20/R42，FR-011）

**Checkpoint**: US3 全部 AS 绿

---

## Phase 6: User Story 4 - 抽取正确性可被证明（Priority: P4）

**Goal**: 双路并行 + 一致性 diff 产生字段级一致率（PRD §2.2 ≥90% 的运行时代理指标；注意一致率≠准确率，plan.md 变更单第 24 项裁定两指标并列）。

**Independent Test**: 对同一份官方 PDF 跑两路抽取，输出逐字段位一致清单 + 总一致率，无需人工标注。

- [ ] T021 [US4] 实现 `backend/agents/vision_parser.py`：栅格化 300 DPI 调 Qwen-VL-Max（ADR-004 原决策保留；经 `VisionParserAgent` 类，MUST NOT 在路由直调）
- [ ] T022 [US4] 实现 `backend/agents/extraction_aggregator.py`：逐字段位三分比对（FR-048）——声明 BOTH 而不同（含一空一有值，FR-040/CHK024 裁定记不一致并保留双方原值、不采信任一路）/ 单路可及不进分母单独计数 / 路级失败按 FR-039；分母排除共享层失败（SC-009）；「双方一致为空」记一致（US4-AS4）
- [ ] T023 [US4] 不一致字段位降级：`NEED_USER_FIX`（BLOCKER，阻断该字段位）；低置信但两路一致 → `MANUAL_TRIAGE`（WARNING）（FR-038、PRD §8.2 R1 拆分后语义）in `backend/engine/verdict.py`
- [ ] T024 [P] [US4] 汇总测试 `tests/backend/test_extraction_aggregator.py`：US4-AS1–AS4 + 两个独立计数器互不吸收（SC-011）+ 一致率可第三方复算（CHK016 输入清单：分母/排除项/分子定义）
- [ ] T025 [P] [US4] 导入图独立性静态检查 `tests/backend/test_agent_import_graph.py`：`deterministic_extractor` 与 `vision_parser` 互不导入；两者仅共同导入 `media_preprocessor`；`extraction_aggregator` 导入两路（FR-036 可自动捕获）

**Checkpoint**: 一致率数字可复算，oracle 上线

---

## Phase 7: User Story 5 - 实体分类触发控权人补齐链（Priority: P5）

**Goal**: 三分类 → Passive NFE 条件必填 → 跨文档控权人表的完整链在规则层可裁决。

**Independent Test**: Passive NFE 且控权人槽位空 → BLOCKER；2 位控权人只附 1 份控权人表 → 跨文档数量不匹配。

- [ ] T026 [US5] 实体三分类判据规则化 `rules/hk/entity_classification.json`（判据出处 `assets/crs-templates/crs-terms-ird.pdf` 受控词条；MUST 恰好命中一类 FR-021；`holder_type=ENTITY` 不可替代三分类）+ `backend/engine/` 求值接入
- [ ] T027 [US5] Passive NFE ⟹ ≥1 控权人条件必填（FR-023）：BLOCKER 并引用触发分类；Active NFE 空槽位合法（US5-AS2）in `backend/engine/structured_validation.py`
- [ ] T028 [US5] 跨文档链接检查 `backend/services/document_intake.py` 扩展：控权人表 `controlled_entities[]`(1–3) 回指实体文档；实体列 N 位控权人要求恰好 N 份控权人表（US5-AS4）；`link_confidence` 为 LOW/NAME_DOB_ONLY/UNLINKED 时降级 MANUAL_TRIAGE（FR-045、SC-010）；Part 4 11×3 矩阵按实体列独立保留不压一维（FR-026）
- [ ] T029 [US5] 控权人门槛参数声明式化 `rules/hk/controlling_person_thresholds.json`：法团 25% / 合伙 0%、`effective_from=2021-01-01`、按 `policy.today` 与实体形式取值（FR-028/R27，0% 语义=每位合伙人都是控权人）；`no_natural_person_control=true` 时高管兜底不得把空值当合法（FR-024）
- [ ] T030 [P] [US5] 链测试 `tests/backend/test_entity_cp_chain.py`：US5-AS1–AS7 全覆盖

**Checkpoint**: P1–P5 全部故事独立可验

---

## Phase 8: Polish & Cross-Cutting

- [ ] T031 监管参数欠账清点：对照 plan.md M/N 表逐项核对 27 参数中仍硬编码于 `backend/engine/completeness.py` 等处的条目，产出声明式化迁移清单并迁 `rules/hk/`（FR-041 收尾；66 个 TIN 选择器 ≠ 27 参数已完成，不得混同）
- [ ] T032 产出 `design/openapi.yaml`：按已裁定方案①——`CRSFormData` 仅在 `contracts/crs-form-data.schema.json` 定义，`$ref` 外链引用（plan.md 变更单第 20 项）
- [ ] T033 变更单第 1–14、19 项文档修订落笔（PM 权属内执行 `specs/prd.md`/`specs/data-spec.md`；`design/` 两处需设计侧确认后改；第 19 项 `CRSFormData` 权威落点需裁定）
- [ ] T034 覆盖率报告：`make test-cov` 出具 `fail_under=80` 达标证明（plan.md §尚未完成；不以测试数量代替覆盖率）
- [ ] T035 指标实测：端到端 ≤30s（PRD §2.2）与一致率首次真实读数；准确率 ≥90% 仍标「无产生机制直至 Phase 6 落地」
- [ ] T036 文档同步：`plan.md` §实现现状/§项目级待办 与 `README.md` 按本清单完成态更新；`.specify` 远端推送补齐（T006 遗留）

---

## Dependencies & Execution Order

- **Phase 0**：无依赖，用户指定本轮唯一承诺；T002 依赖 T001，T005 依赖 T002/T004，T006 依赖 T005。
- **Phase 1 → 2 → 3/6/7**：T007 依赖必须在 T009/T013 同批（V1 裁定）；T009→T010/T011→(T013, T021, T022)。
- **Phase 4/5**：仅依赖既有运行接口，可与 Phase 2/3 并行开工（不同文件）。
- **US4（P4）依赖 US1 产物**：一致率分母需要 T011 核实结论 + T013/T021 两路输出。
- **US5（P5）**依赖 T008 规则落点；T028 依赖 Phase 3 的受理服务。
- 故事内：测试先写并确认失败 → 模型/规则 → 服务 → 端点。

## Parallel Example

```bash
# Phase 0 内 T001/T003 可同时开始（不同文件）；
# Phase 2 完成后，Phase 3/4/5 可由不同人并行。
```

## Implementation Strategy

- **本轮 MVP = Phase 0**（联调就绪，半小时量级）。**完成并验证后 STOP**。
- 后续增量：Phase 1–3（HK 入口可用，竞赛故事线升级的前提）→ Phase 4/5（补缺口，快）→ Phase 6（一致率 oracle）→ Phase 7（控权人链）→ Phase 8。
- 若竞赛演示故事线维持「结构化 JSON 提交」，Phase 1+ 可整体延后——此决策点属于用户/团队（对应昨日 review 中拓扑与故事线问题）。

## Notes

- 路径约定以 AGENTS.md 结构为准；`backend/agents/` 新增模块遵守 plan.md §Structure Decision 导入图。
- 每个 Phase 结束提交一次（或按逻辑组）；不引入未经团队批准的依赖（V1 已批准 PDF 解析一项）。
- `specs/`、`design/`、`docs/` 修改仅限 T033/T034 所列 PM 权属项。
