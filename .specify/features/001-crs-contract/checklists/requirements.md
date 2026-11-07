# Requirements Quality Checklist: CRS 自我证明表数据契约与抽取路径修订（HK/IRD）

**Purpose**: 对 `spec.md` 做「英文的单元测试」——检验需求本身写得是否完备、清晰、一致、可度量、可回溯，而不是检验实现是否正确。
**Created**: 2026-11-04
**Feature**: [spec.md](../spec.md) ｜ 证据基线 [mapping-matrix.csv](../mapping-matrix.csv)

**Review Ownership**: 本清单为评审人（PM）所有的需求质量评审工件。仅当评审人判定某项需求质量标准已满足时才标记 `[x]`。生成方 MUST NOT 自行勾选——以下 28 项全部保持未勾选状态。
**Marker Semantics**: `[x]` 表示该项需求质量标准已被评审并满足，**不**表示实现工作已完成。

**生成参数**（`commands/checklist.md` 第 3 步在用户授权代决下采用默认值）：深度 = Standard；受众 = 评审人（PM-owned spec 评审）；焦点 = 相关度最高的两簇，即「数据契约完备性」与「合规可追溯性」。

## 需求完备性

- [ ] CHK001 映射矩阵中 14 条「中」缺口与 4 条「低」缺口是否各自有明确处置，或已显式声明本轮不处置？FR-034 只强制了 24 条「严重」。[Completeness, Gap]
- [ ] CHK002 文档状态机（受理 → 抽取 → 裁决 → 待人工 → 结案）是否在需求中定义？[Gap]
- [ ] CHK003 「部分纳入」这一处置类别的边界是否定义清楚——R22 / R23 究竟哪部分纳入、哪部分排除？[Clarity, Spec §FR-034]
- [ ] CHK004 术语表 `crs-terms-ird.pdf` 中的 20+ 受控词条是否被声明为分类判据来源，还是仅作参考材料？[Gap]
- [ ] CHK005 数据量假设（单次受理文档数上限、单实体控权人数上限）是否在需求中给出？[Gap]

## 需求清晰度

- [ ] CHK006 FR-045 的「置信度标记」是否定义了阈值或阈值的取值来源？[Ambiguity, Spec §FR-045]
- [ ] CHK007 「理由 B 的解释文本达到最小可读长度」是否给出了具体字符数？[Ambiguity, Spec §User Story 2 / §FR-014]
- [ ] CHK008 FR-036 的「字段定位与文本归属逻辑相互独立」是否给出了可判定的边界示例？[Clarity, Spec §FR-036]
- [ ] CHK009 FR-017 的「实际管理地」与「税收居民地」在何种情形下可同时存在，是否给出判据？[Ambiguity, Spec §FR-017]
- [ ] CHK010 FR-028 的「按实体形式取值」是否枚举了实体形式的完整清单（法团 / 合伙 / 其他）？[Clarity, Spec §FR-028]

## 需求一致性

- [ ] CHK011 FR-016 的「并列保留 + WARNING」与 FR-033 的「星号字段位缺失 = BLOCKER」是否会在同一字段位上产生冲突裁决？[Conflict, Spec §FR-016 / §FR-033]
- [ ] CHK012 当持有人申报 6 个法域而系统只配置了 HK 时，FR-013（基数无上限）与 FR-042（未配置法域 → `MANUAL_TRIAGE`）叠加后的裁决结果是否唯一确定？[Conflict, Spec §FR-013 / §FR-042]
- [ ] CHK013 spec 使用中文译名（被动非财务实体）而 `mapping-matrix.csv` 与 PRD 使用英文（Passive NFE）；是否已声明单一权威术语来源与映射表？[Consistency, Assumption]
- [ ] CHK014 FR-032 把签名存在性判为「由上游判定」，但该上游能力是否在需求中被定义？[Dependency, Gap]
- [ ] CHK015 FR-046 扩展的加密字段清单与 PRD §4.2「存储加密」行的既有清单是否已对齐，而非各说各话？[Conflict, Spec §FR-046]

## 验收标准质量

- [ ] CHK016 SC-004 的「第三方可独立复算」是否定义了复算所需的完整输入清单？[Measurability, Spec §SC-004]
- [ ] CHK017 SC-006 的 2020-12-31 vs 2021-01-01 双日期测试是否指定了实体形式——只有合伙的 0% 门槛会产生判定差异。[Measurability, Spec §SC-006]
- [ ] CHK018 SC-002 的分母「8」是否固定绑定到 `mapping-matrix.csv` 中 asterisk=YES 的行集合，且该集合变更时 SC 是否要求同步？[Measurability, Spec §SC-002]
- [ ] CHK019 SC-009 与 SC-010 是否各有对应的 FR 使其可被实现，而不只是度量愿望？[Traceability, Spec §FR-037 / §FR-045]
- [ ] CHK020 是否存在任何 SC 无法在「本轮不产出实现代码」的约束下被验证？若有，是否已标注为延后而非默认可达？[Measurability, Assumption]

## 场景与边界覆盖

- [ ] CHK021 收到一份含两个持有人的文档时，FR-005 要求的是拒收、拆分、还是只取第一个？需求是否指定？[Edge Case, Gap, Spec §FR-005]
- [ ] CHK022 恢复类场景是否有需求——抽取中途失败后重跑，是否要求幂等？[Gap, Recovery]
- [ ] CHK023 R27 的合伙 0% 门槛意味着「每位合伙人都是控权人」；当合伙人数超过表单 8 个槽位时，需求是否指定处理方式？[Edge Case, Spec §FR-028]
- [ ] CHK024 两路对同一字段位一个返回空、一个返回值时，属于「不一致」还是「一方缺失」？FR-040 只覆盖了「双方一致为空」。[Ambiguity, Spec §FR-040]
- [ ] CHK025 续页（FR-004）与「一份文档 = 一个持有人」（FR-005）在续页被单独提交时是否冲突？[Conflict, Edge Case]

## 依赖与假设

- [ ] CHK026 「OECD CRS XML Schema 元素名未经核实」这一假设是否声明了核实责任人与核实时限？[Assumption]
- [ ] CHK027 `rules/` 目录为空、`specs/data-spec.md` §3 却引用两个不存在的规则文件——这一冲突是否已在变更单中登记？[Conflict, Assumption]
- [ ] CHK028 FR-041 要求监管参数存放于外部规则配置，但规则引擎尚未实现；该需求的可实现前置条件是否已声明？[Dependency, Spec §FR-041]

## Notes

- 仅在评审确认需求质量标准已满足后标记 `[x]`；仍需澄清、修正或评审的项保持未勾选。
- 全部 28 项均带至少一个可追溯引用（`[Spec §…]` / `[Gap]` / `[Ambiguity]` / `[Conflict]` / `[Assumption]` / `[Dependency]`），满足 `commands/checklist.md` 要求的 ≥80% 可追溯率（实际 100%）。
- 本清单不含任何「Verify / Test / Confirm + 实现行为」型条目——那属于实现测试，不属于需求质量测试。
- CHK011、CHK012、CHK015、CHK025 是本轮扫描中识别出的**真实潜在冲突**，建议优先评审。
- CHK001、CHK021、CHK024 指向 `spec.md` 中确实尚未写明的决策点；若评审认为需要补齐，应回到 spec 修订而非在本清单勾选。
