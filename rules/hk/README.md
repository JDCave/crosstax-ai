# rules/hk — 法域分层策略文件

本目录存放 HK 法域的**逐法域策略文件**（policy files）。加载约定对所有法域目录一致，由
`backend/engine/rule_loader.py::load_jurisdiction_policy_file` 唯一实现：

1. **路径与命名**：`rules/<jurisdiction>/<filename>.json`，jurisdiction 为小写两字码（`[a-z]{2]`），
   filename 为小写标识符（`[a-z0-9_]+`）。不合规路径直接拒绝，不做目录遍历。
2. **大小上限**：单文件 64 KiB（`JURISDICTION_FILE_MAX_BYTES = 65_536`），超限即失败，不截断。
3. **结构校验**：每个文件由调用方提供的 Pydantic 模型在加载时 `extra="forbid"` 严格校验；
   校验失败即抛出，不回退默认值。
4. **身份标识**：返回值第二元为解析后内容的 canonical SHA-256（`reproducibility.canonical_hash`），
   调用方将其写入执行上下文（如 `form_policy_id`），使每次裁决可回溯到确切的策略字节。
5. **与 DB 规则载体的关系（ADR-011）**：TIN 正则/算法等活动规则运行时仍来自数据库
   `rule_versions.rules`；本目录文件是**评审入库的注册输入**（git 审阅、哈希稳定），承载无法用
   `{法域: {regex, algorithm}} 表达的维度（字段位、实体形式、生效日期、文档类型）。
6. **生效日期**：带法律生效期的参数（如控权人门槛 2021-01-01）MUST 以 `effective_from` 字段表达
   并按 `policy.today` 取值，MUST NOT 塌缩为常数（FR-028 / FR-041）。

## 现有文件

| 文件 | 模型（校验处） | 消费方 | 提供的参数 |
|---|---|---|---|
| `form_policy.json` | `structured_validation.FormPolicy` | `load_form_policy()` | 理由 B 最小长度、必填字段清单、实体分类枚举、可信链接置信度、国家码表、POEM/授权书 capacities |

## 规划中的落点（来自 tasks.md）

- `entity_classification.json`（T026）：三分类判据，词条出处 `assets/crs-templates/crs-terms-ird.pdf`
- `controlling_person_thresholds.json`（T029）：法团 25% / 合伙 0%，`effective_from=2021-01-01`
