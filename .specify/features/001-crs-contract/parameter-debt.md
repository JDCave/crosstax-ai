# T031 监管参数欠账清点与声明式化迁移清单（FR-041 收尾）

**清点日期**: 2026-11-12 ｜ **基线**: plan.md §规则表达力测算（N=27）｜ **核验方式**: 逐项对 `backend/engine/`、`backend/agents/`、`rules/`、`contracts/` 实际代码/配置比对

**重要区分**：`rules_global_v4.json` 的 66 个 TIN 选择器 ≠ 27 个监管参数已完成——前者只覆盖下表 #1–#3 的「格式与算法」两维，其余 24 项在本清单中逐项定性。

处置类别：**CONFIG** = 已在外部配置（rules/hk/ 或 DB 快照）｜**SCHEMA** = 声明式落点在契约 JSON Schema（基数/枚举类）｜**ALGO** = 确定性算法/格式转换，非参数（留在代码，此处记录理由）｜**POLICY-IN** = 由调用方运行期传入｜**MIGRATED-1112** = 本轮从 Python 迁入配置｜**TODO** = 功能未实现，实现时 MUST 落配置（附字段建议）

| # | 参数（plan.md M/N 行） | 出处 R | 处置 | 落点 / 结论 |
|---|---|---|---|---|
| 1 | TIN 格式正则（22 法域 66 选择器） | R29 | CONFIG | DB `rule_versions.rules`（ADR-011），`rules/rules_global_v4.json` 为注册输入 |
| 2 | TIN 校验算法选择 | R29 | CONFIG | 规则 JSON `algorithm` 字段；算子本体是代码实现（如 `HKID_WEIGHT`），选择是数据 |
| 3 | TIN 清洗（去空白/括号/连字符、转大写） | R29 | ALGO | `tin_validator.py:102` 统一归一化，全法域一致、非法域参数；`API_INTEGRATION.md:96` 已文档化为引擎行为 |
| 4 | 控权人门槛：法团 25% | R27 | CONFIG | `rules/hk/controlling_person_thresholds.json`（T029） |
| 5 | 控权人门槛：合伙 0%（0%=每位合伙人） | R27 | CONFIG | 同上，含 `semantics` 注记 |
| 6 | 门槛生效日期 2021-01-01 | R27 | CONFIG | 同上 `effective_from`；早于生效日 → `BEFORE_EFFECTIVE_FROM` → MANUAL_TRIAGE（SC-006 有测试） |
| 7 | 罚则级别（第三级） | R46 | TODO | 全仓无实现（grep 证实）；实现 R46 披露时落 `rules/hk/penalties.json`：`{tier, amount, currency, effective_from, source}` |
| 8 | 罚则金额 $10,000 | R46 | TODO | 同上；2025-12-09 咨询拟调额，硬印即腐化 |
| 9 | 变更通知期限 30 天 | R44/R45 | TODO | 全仓无实现；实现「reason to know」重取逻辑时落 `rules/hk/`（建议字段 `notification_period_days: 30`） |
| 10 | 无 TIN 理由枚举 A/B/C | R30 | SCHEMA | `structured_contracts.TaxResidency.no_tin_reason: Literal["A","B","C"]` + 契约 enum——枚举的权威落点即 schema |
| 11 | 理由 B 最小长度 | R31 | MIGRATED-1112 | 结构化路径此前已读 `form_policy.reason_b_min_length`；**本轮**清除 `completeness.py:59` 残留字面量 `< 5`，`check_completeness` 改收显式参数，`validation.py` 从同一配置传入 |
| 12 | 理由 C 适用前提 | R34 | ALGO | FR-020 的「不得自动判定」是结构性保证：`EXEMPTION_REVIEW_REQUIRED` 恒发 WARNING——把它做成可关开关反而违反 FR-020 |
| 13 | 派生等值：个人/控权人 HK TIN=HKID | R32 | MIGRATED-1112 | `form_policy.derived_equalities`（jurisdiction+holder_type→source_field+tin_type），Python 不再特判 `"HK"` |
| 14 | 派生等值：实体 HK TIN=BR | R32 | MIGRATED-1112 | 同上；归一化正则与 #3 同源 |
| 15 | 实体三分类判据 | R21 | CONFIG | `rules/hk/entity_classification.json`（受控词条，T026）+ `form_policy.entity_types`；求值模型 `EntityClassificationFile` 加载校验 |
| 16 | Passive NFE ⟹ ≥1 控权人 | R23 | CONFIG | 判定条件读 `form_policy.passive_entity_type`，规则数据驱动 |
| 17 | 无自然人控制 ⟹ 高管兜底 | R24 | CONFIG | `form_policy.power_of_attorney_capacities` / `declared_non_poa_capacities` 承载 capacity 词表；「兜底不得当空值合法」为 FR-024 结构语义（ALGO） |
| 18 | 星号→BLOCKER 严重度映射 | R41 | 记录 | 严重度按逐检查点字面量编码，每个点位可由 `mapping-matrix.csv` asterisk 列回溯（R06/R07/R09/R14/R16/R19/R28/R29 → BLOCKER）。未参数化理由：无重配需求，且错误面=合规面，改动应走评审而非配置 |
| 19 | 「Not compulsory」清单 | R20 | CONFIG | 不在 `form_policy.required_fields` 即不判缺（birth_place 缺席=声明）；FR-011 有测试钉住 |
| 20 | 「not applicable」合法空值 | R42 | ALGO | FR-035 语义规则，非可调参数 |
| 21 | 一文档一持有人 | R04 | SCHEMA/ALGO | FR-005 规格常量 =1（法律基数，非监管参数）；契约 `holders_declared minimum:1`；两处 MUST NOT 可配置化 |
| 22 | 控权人回指基数 1..3 | R25 | SCHEMA | 契约 `controlled_entities minItems:1 maxItems:3` |
| 23 | 税收居民地基数 ≥1 | R28 | SCHEMA | 契约 `tax_residencies minItems:1`；无上限，实际界由 1 MiB 推导（FR-013）；旧格式 `max_length=20` 为兼容冻结（plan §实现现状） |
| 24 | 签署日期 ≤ policy.today | R40 | POLICY-IN | `ValidationPolicy.today` 调用方传入 |
| 25 | dd/mm/yyyy → ISO | R12/R40 | ALGO | 格式转换算法，无参数值 |
| 26 | 地址国家码 ISO 清单 | R16 | CONFIG | `form_policy.country_codes`（249 码 + 来源 URL + SHA-256 溯源） |
| 27 | 链接置信度阈值 | R03 | CONFIG | `form_policy.trusted_link_confidences`（现=["HIGH"]）；HIGH 判据在 `document_linking.establish_link`（FR-045 语义） |

## 本轮实际迁移（MIGRATED-1112，已全部验证）

1. **`FormPolicy`/`load_form_policy` 迁至 `backend/engine/regulatory_parameters.py`**——法域策略参数的规范模块；原导入路径（`structured_validation`）的引用方全部改指权威落点。
2. **`completeness.py` 理由 B 阈值去硬编码**——`check_completeness(form, policy, reason_b_min_length)` 显式注入，legacy 引擎与结构化路径共用同一 `rules/hk/form_policy.json` 值；测试改为读配置而非私有常量。
3. **HK 派生等值去特判**——`structured_validation` 的 `residence.jurisdiction == "HK"` 两处（变体选择 + 等值块）改由 `form_policy.derived_equalities` 三条记录驱动（HK×IND/CP/ENTITY）；错误码 `<JUR>_IDENTITY_EVIDENCE_MISSING / <JUR>_TIN_IDENTITY_MISMATCH` 对 HK 逐字节不变；`finish()` 审查面扫描按 `*_identity_equality` 后缀识别，新增法域零改码。

**验证**：374 passed / 12 skipped；`HK_TIN_IDENTITY_MISMATCH` 相关既有测试（US3-AS1/AS2、official cases、impact 回归、`TASK_BUILD_MISMATCH` 指纹链路）全绿；mypy strict + ruff 全通过。`form_policy_id` 随内容哈希变化（测试仅断言真值，不钉字面量）。

## 遗留（诚实标注）

- #7/#8/#9 属「功能未实现」而非「参数未声明化」——本轮只登记落点约定，不留空壳配置；
- 门槛评估器（T029 `regulatory_parameters`）尚无运行期消费方：持股/表决权事实未入契约（plan §尚未完成「输入缺口」），接线在控权人持股输入落地时；
- #18 星号映射若未来出现「按法域调整严重度」需求，应设计为规则条目而非散落 if。
