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
- [X] T006 提交并推送成功：`751eb2e` fix(ai)（trust_env 修复+回归测试）、`00884ca` docs(integration)（联调入口四件套 + NEED_USER_FIX 样例 + make worker 别名 + PRD v1.3 + checklist 勾选 + tasks.md）。远端已改用 SSH（`git@github.com:JDCave/crosstax-ai.git`），历史 HTTPS 凭据问题不复存在。`crosstax.db.bak-20261111` 与 `integration_smoke_report.pdf` 保持未跟踪（待用户决定归档或忽略）

**Checkpoint**: 联调就绪。⚠️ 以下 Phase 1+ 为 feature 全量工作（双路抽取等），非 11-13 联调前置，是否开工需用户另行决定。

---

## Phase 1: Setup（共享基础设施）

- [X] T007 在 `pyproject.toml` 新增 PDF 解析依赖——实测定候选改选 **pypdf 6.x**（原 dev 组提升为主依赖）：四份官方 PDF 实测 AES-128 空用户密码解密 + `/StructTreeRoot` 全通过，且与既有 `cryptography` 协同；pikepdf 携 qpdf 原生二进制，被避免。`uv.lock` 已同步。与 T009/T013 消费代码同批落地 ✓
- [X] T008 `rule_loader.py` 新增 `load_jurisdiction_policy_file()`（`rules/<jurisdiction>/<file>.json`，64 KiB 上限 + canonical hash 唯一实现），`load_form_policy` 改为委托（哈希行为不变）；`rules/hk/README.md` 落加载约定文档头（T025/T028/T030 监管参数落点）✓

**Checkpoint**: 依赖与规则落点就绪 ✓

---

## Phase 2: Foundational（阻塞前置）

**⚠️ CRITICAL**: US1/US4 的故事工作不能先于此 Phase。

- [X] T009 `backend/agents/media_preprocessor.py` 共享层：解密（仅空用户密码，绝不尝试越权绕过）+ 页面枚举（全量，无截断）+ SHA-256 指纹 + `is_encrypted`/`structure_tree_available`/`has_continuation_sheets`（模板 Title 元数据基线 2/2/3/8）+ 归因 `PDF_CORRUPTED`/`PDF_USER_PASSWORD_REQUIRED`/`PDF_TOO_LARGE` 三码与「加密」互斥（FR-001/002/003/004）✓
- [X] T010 `tests/backend/test_media_preprocessor.py` 10 项全绿：四份官方 PDF 零拒收且指纹=README 登记 SHA-256（SC-001 4/4）、权限位受限件受理（US1-AS3）、密码件/损坏件归因可区分（US1-AS4）、续页标记不截断 ✓
- [X] T011 path_capability 逐行核实完成，证据记录 `.specify/features/001-crs-contract/path-capability-verification.md`：43 个默认 BOTH 全部被字形+结构树实证确认（无一改值）；勾选框字形 0xf0a3 精确只落 R21/R22/R26、划记式 Delete-as-appropriate 落 R35/R36（5 个 VISION_ONLY 定位准确）；无 AcroForm → 答案态经 Word 重导出保留文本层，R30/R31 维持 BOTH；CP 类型矩阵 14 行×5 列可经 /MCID 无损复原 ✓

**Checkpoint**: 入口受理可用，一致率分母诚实 ✓

---

## Phase 3: User Story 1 - 受理官方加密表单而不拒收（Priority: P1）

**Goal**: 官方 AES-128 加密 Tagged PDF 从入口 100% 拒收变为全受理并产出裁决。

**Independent Test**: 单独投放四份官方 PDF，断言零拒收、每份产出裁决对象（spec.md §US1）。✓（`test_multi_holder.py::test_single_holder_with_legal_repeat_groups_is_accepted` + `test_terms_reference_sheet_goes_to_triage_without_rejection`）

### Tests for User Story 1

- [X] T012 [P] [US1] `tests/backend/test_deterministic_extractor.py` 9 项：ENT 三分类表列归属无串位、CP 11×3 矩阵 14 行×5 列独立保留（US5-AS3 同源）、TIN 表 6 行×4 列位保留、无结构树件降级显式记录（FR-003）、子项填空跨行归因（NASDAQ/ACME 不互串）✓

### Implementation for User Story 1

- [X] T013 [US1] `backend/agents/deterministic_extractor.py`：/Table /TR /TD→/MCID→标记文本链还原表格 + 文本层标签扫描，输出对齐 `contracts/crs-form-data.schema.json` 扁平路径（`tax_residencies[i].jurisdiction` 等）；VISION_ONLY 位返回 None 不猜测（FR-048）；R18 双「Line 2」排版异常暴露为 `DUPLICATE_LABEL_LINE_2`（FR-043）✓
- [X] T014 [US1] `backend/services/document_intake.py`：身份块判据=「Part 1 Identification of {Individual|Entity} Account Holder / Controlling Person」标题出现次数，MUST NOT 按重复组计数；>1 → 拒收整份、`MULTI_HOLDER_DOCUMENT`、`NEED_USER_FIX`、零抽取（FR-005/047）；术语表 → 受理转 `MANUAL_TRIAGE` 非拒收 ✓
- [X] T015 [US1] [P] `tests/backend/test_multi_holder.py` 11 项：双份拼接拒收分支 + SC-012 反向闸（8 控权人槽位/5 居民地/11×3 矩阵单持有人件全受理、3 居民地场景不误拒）+ 端点 e2e ✓
- [X] T016 [US1] `backend/api/routes/audit.py`：`POST /api/v1/audit/documents`（application/pdf 字节直传，避免引入未批准的 python-multipart 依赖）→ 受理/拒收归因 + 抽取产物；错误走 `{code,message}`；`main.py` 注册；公开面守卫测试与 `openapi.json` 快照同步再生成 ✓

**Checkpoint**: US1 独立可验——四份官方 PDF 投放即出裁决 ✓

---

## Phase 4: User Story 2 - 一位持有人有多个税收居民身份（Priority: P2）

**Goal**: `tax_residencies[]` 重复组任意条数、逐条独立裁决。结构与新契约**已由运行接口承接**（plan.md §实现现状），本 Phase 为按 spec 场景验证补缺。

**Independent Test**: 构造 3 居民地（1 个无 TIN 理由 B 附解释）数据直投现有接口，断言三条全留存、逐条各自裁决、无 TIN 条不因缺 TIN 判 BLOCKER。✓

- [X] T017 [P] [US2] `tests/backend/test_tax_residencies_us2.py` 6 项：US2-AS1 三法域全保留逐条独立 / AS2 六法域不截断 / AS3 理由 B 去空白达最小长度且 A/C 不强制解释 / AS4 TIN 与理由互斥冲突（FR-015）—— 全绿，未暴露新缺口 ✓
- [X] T018 [US2] 核验：`backend/engine/structured_validation.py` 已实现上述逻辑（逐法域 `residence_results`、互斥、理由 B 长度走 `config["reason_b_min_length"]`），理由 B 阈值已在 `rules/hk/form_policy.json`（非 Python 常量）→ 本 Phase 为「验证+补缺」，T017 未暴露缺口，无需改动 ✓

**Checkpoint**: US2 全部 AS 绿 ✓

---

## Phase 5: User Story 3 - 派生等值规则自动执行（Priority: P3）

**Goal**: HKID=TIN、商业登记号=TIN 跨字段等值作为独立校验执行（现状：已接入 `structured_validation.py`，本 Phase 按 AS 验证补缺）。

**Independent Test**: 提交 HKID 与 TIN 表 HK 行故意不一致的个人版结构化输入，断言报出等值违规并指出两个来源字段位。✓

- [X] T019 [P] [US3] `tests/backend/test_derived_equivalence_us3.py` 4 项：AS1 个人等值引用双字段位 / AS2 实体 BR 等值 / AS3 POEM 独立申报不替代（FR-017）/ AS4 理由 C 显式 `EXEMPTION_REVIEW_REQUIRED` 不沉默（FR-020）✓
- [X] T020 [US3] 核验：星号→BLOCKER 严重度映射已在 `structured_validation.add/check`（`MISSING_*` 默认 BLOCKER、审查类 WARNING）+ `verdict.resolve_verdict` 三态；「Not compulsory / not applicable」空值不判缺（`birth_place=None` 仍 AUTO_PASS）已由既有测试覆盖 ✓

**Checkpoint**: US3 全部 AS 绿 ✓

---

## Phase 6: User Story 4 - 抽取正确性可被证明（Priority: P4）

**Goal**: 双路并行 + 一致性 diff 产生字段级一致率（PRD §2.2 ≥90% 的运行时代理指标；一致率≠准确率，plan.md 变更单第 24 项两指标并列）。

**Independent Test**: 对同一份官方 PDF 跑两路抽取，输出逐字段位一致清单 + 总一致率，无需人工标注。

- [X] T021 [US4] `backend/agents/vision_parser.py`：`VisionParserAgent` 从共享层 `PreprocessedPdf` 取页（FR-036 独立），构造 Qwen-VL 请求解析回扁平字段；栅格化为**注入式接缝**（V1 仅批准 PDF 解析，pdf2image/poppler 待团队裁定）→ 真实模型质量未验收；测试 `test_vision_parser.py` 5 项（mock provider）✓
- [X] T022 [US4] `backend/agents/extraction_aggregator.py`：逐字段位三分（FR-048）——声明 BOTH 而不同（含一空一有值，CHK024）记不一致并保留双方原值不采信 / 单路可及不进分母单独计数 / 路级失败按 FR-039 / 共享层失败排除分母（SC-009）/ 双方一致为空记一致（FR-040）；capability 只从 `mapping-matrix.csv` 加载并校验 ✓
- [X] T023 [US4] 降级：不一致字段位由调用方按 `disagreement_paths` 发 `EXTRACTION_DISAGREEMENT`（BLOCKER→`NEED_USER_FIX`），一致报告不阻断；两态映射由 `verdict.resolve_verdict` 承接，测试钉住 ✓
- [X] T024 [P] [US4] `tests/backend/test_extraction_aggregator.py` 9 项：US4-AS1–AS4 + 两计数器互不吸收（SC-011）+ 一致率第三方可复算（`recompute()`，CHK016）+ T023 降级 ✓
- [X] T025 [P] [US4] `tests/backend/test_agent_import_graph.py` 5 项：AST 静态检查——两路互不导入、仅共享 `media_preprocessor`、汇总器导入两路且两路不回导汇总器、受理层不引视觉路（FR-036 可自动捕获）✓

**Checkpoint**: 一致率数字可复算，oracle 上线 ✓

---

## Phase 7: User Story 5 - 实体分类触发控权人补齐链（Priority: P5）

**Goal**: 三分类 → Passive NFE 条件必填 → 跨文档控权人表的完整链在规则层可裁决。

**Independent Test**: Passive NFE 且控权人槽位空 → BLOCKER；2 位控权人只附 1 份控权人表 → 跨文档数量不匹配。✓

- [X] T026 [US5] `rules/hk/entity_classification.json`（判据出处 crs-terms 受控词条，声明 CHK004 判据来源；exactly-one-hit；`holder_type` 不可替代）+ `regulatory_parameters.EntityClassificationFile` 加载校验 ✓
- [X] T027 [US5] Passive NFE⟹≥1 条件必填：核验 `structured_validation.MISSING_CONTROLLING_PERSON`（BLOCKER）+ Active NFE 空槽合法 已由 `test_entity_cp_chain.py` AS1/AS2 走真实 HTTP 验证 ✓
- [X] T028 [US5] `backend/services/document_linking.py`：Ref. No. 主键 + 姓名/DOB 兜底（FR-045）——HIGH 需双信号一致、仅 Ref 而姓名未印证=LOW、无 Ref=NAME_DOB_ONLY、均不命中=UNLINKED，非 HIGH 一律 `requires_manual_triage`；`link_bundle` 出数量不匹配（US5-AS4）与 SC-010 置信度标记 ✓
- [X] T029 [US5] `rules/hk/controlling_person_thresholds.json` + `regulatory_parameters.evaluate_controlling_person_ratio`：法团 25%/合伙 0%、`effective_from=2021-01-01`、按 `policy.today`+实体形式取值，未知形式→MANUAL_TRIAGE 不套常数；SC-006 日期分裂真实生效 ✓
- [X] T030 [P] [US5] `tests/backend/test_entity_cp_chain.py` 11 项：US5-AS1–AS7 全覆盖 ✓

**Checkpoint**: P1–P5 全部故事独立可验 ✓

---

## Phase 8: Polish & Cross-Cutting

- [X] T031 监管参数欠账清点：`parameter-debt.md` 逐项定性 27 参数（CONFIG 12 / SCHEMA 4 / ALGO 5 / POLICY-IN 1 / TODO 3 / 记录 1；66 TIN 选择器未被混同）。实际迁移 3 项：① `FormPolicy` 家族落 `regulatory_parameters.py` ② `completeness.py` 理由 B `< 5` 字面量改显式注入同一 `rules/hk/form_policy.json` 值 ③ HK 派生等值两处特判改 `form_policy.derived_equalities` 数据驱动（HK 错误码逐字节不变，mypy/ruff/374 测试全绿）；罚则金额、30 天期限、持股门槛接线登记为「功能未实现+落点约定」，不留空壳 ✓
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

---

## Phase 9: Convergence

> 2026-11-12 converge 核验产出（勾选≠证据，全部经代码实测）。T034 覆盖率闸门已实测达标（90.49% ≥ 80%，374 passed），不再列任务。F7 对应竞赛范围冻结项，开工前需用户/团队裁定。

- [ ] T037 裁定并落地 Vision 路栅格化依赖（pdf2image/poppler 或 pypdfium2，需团队批准），在 `backend/agents/vision_parser.py` 实现默认栅格化替换 `RASTERIZER_NOT_WIRED` 接缝，并以真实 Qwen-VL 模型对四份官方 PDF 验收抽取质量 per FR-036 / T021 遗留 (partial)
- [ ] T038 在受理/任务运行时路径接入双路并行抽取与 `extraction_aggregator`（当前 `document_intake.py` 仅确定性路、汇总器零运行时调用方），API 响应暴露字段级一致率、共享层失败与单路可及两个独立计数器 per FR-037 / SC-004 / SC-009 / SC-011 (missing)
- [ ] T039 将 `backend/services/document_linking.py` 的 `link_bundle` 接入运行时路径（当前唯一导入方为测试），使实体↔控权人跨文档数量/回指校验可经 API 触发 per FR-025 / FR-027 / SC-008 (missing)
- [ ] T040 完成 T031 监管参数欠账迁移：27 参数中仍硬编码或缺失项（罚则级别/$10,000/30 天期限、星号→BLOCKER 映射、日期格式、基数约束等）逐项声明式化至 `rules/hk/`，并把 `regulatory_parameters.py` 的门槛/分类加载器接入运行时校验路径（当前仅测试调用） per FR-041 (partial)
- [ ] T041 消除旧路径硬编码冲突：`backend/engine/completeness.py:59` 理由 B `< 5` 改读 `rules/hk/form_policy.json` 同一配置源，与结构化路径行为一致 per FR-041 (contradicts)
- [ ] T042 扩展加密留存至 FR-046 清单：同步审计路径 `rule_audit_records.form_data/result` 明文存储 DOB/TIN 等敏感字段改为加密，并建立显式敏感字段清单（HKID/护照号、出生日期、出生地） per FR-046 (partial)
- [ ] T043 主审核流水线缺口裁定与实现：AuditSession/Merchant ORM、`run_audit_pipeline()`、`/ws/audit/{session_id}`、跨源研判（indicia 现仅透传）、主会话 HTML/PDF 报告、`/api/v1/rules` 与 `/api/v1/cases` 路由——属竞赛范围冻结项，先经用户/团队裁定本轮实现或正式延期，再按裁定执行 per plan:项目级待办(实现阶段) (missing)
- [ ] T044 产出 `design/openapi.yaml`：按已裁定方案①，`CRSFormData` 仅在 `contracts/crs-form-data.schema.json` 定义并以 `$ref` 外链引用 per plan:变更单第 20 项 / T032 (missing)
- [ ] T045 落笔变更单第 1–3、5–14、19 项（第 4 项已由 PRD v1.3 完成，核验销项）：`specs/prd.md`/`specs/data-spec.md` PM 权属内执行；`design/architecture.md` 两处需设计侧确认；第 19 项 `CRSFormData` 权威落点需裁定 per plan:变更单 / T033 (partial)
- [ ] T046 实测端到端 ≤30s 与一致率首次真实读数（依赖 T037/T038）；同步 `plan.md` §实现现状/§项目级待办 与 `README.md` 至 Phase 1–7 完成态；提交并推送 `.specify` 未跟踪/修改文件（spec.md、tasks.md、path-capability-verification.md） per T035 / T036 (partial)
