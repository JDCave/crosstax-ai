当前全球版本见 [GLOBAL_COVERAGE.md](GLOBAL_COVERAGE.md)，配置为 `rules_global_v3.json`。以下内容保留原三法域竞赛基线说明。

# 来源支持的规则基线与 Case A-E

此目录保存竞赛可执行规则配置；不是各国税号的完整法律规则库，也不查询号码真实性。
来源核对日期：2026-11-02。所有标识类型均区分主体，配置内保留 source_url、source_section、verification_level。

## 版本

- rules_v1_base.json：CN/HK 规则基线，采用规则结构 schema_version=2。
- rules_v2_patch.json：加入 SG 后的完整规则快照。名称沿用 PRD，但文件本身不是增量 merge patch。
- 文件版本 v1/v2 与 JSON schema_version=2 是不同概念。

## 官方资料与范围

| 法域 | 来源 | 配置标识 |
| --- | --- | --- |
| CN | https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/china-tin.pdf Section II | CN_ID、CN_LEGACY_TIN、CN_ENTITY_TIN |
| HK | https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/hong-kong-tin.pdf Section II | HKID、HK_BR |
| SG | https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/singapore-tin.pdf Section II | SG_NRIC、SG_FIN、SG_UEN_ROB、SG_UEN_ROC、SG_UEN_OTHER |

CN_ID、HKID、SG_NRIC 调用已有校验位算子。官方 TIN 文档作为类型与结构依据，
不代表这些文档公布了全部校验位公式；算法依据与限制见 backend/engine/README.md。
其余标识为 FORMAT_ONLY：不验证企业校验位、年份、注册机关、有效登记或 FIN 校验位。
CN_ENTITY_TIN 按 OECD 所列 18 位旧式结构表达，不宣称完整覆盖所有 USCC；未支持的标识应人工复核。
不支持中国护照等其他个人类型、SG 外国企业 UEN、ASGD/ITR 等全部例外，后续需补充专门规则。
企业不得使用个人身份证算法。缺失/不匹配的主体或 tin_type 返回 WARNING: UNSUPPORTED_TIN_TYPE，进入人工复核。

## 命令

```bash
# 不访问数据库，运行固定业务日期 2026-11-02 下的五个 JSON Case。
uv run python -m backend.cli.demo_cases
# 同样先跑五 Case，再保存批准规则，并将最新完整版本激活到现有数据库。
uv run python -m backend.cli.demo_cases --install
```

install 显式授权竞赛规则基线批准与激活，重复执行不增加相同规则版本，已激活时不增加 revision。
若版本此前被拒绝则停止，不覆盖其状态。不得将该命令用于未经核对的外来规则文件。
生产管理仍使用 rule_engine register/approve/activate 的分离流程。
规则 JSON 可直接由其他后端生成并传给 RulePublisher，不需要先抓取资料。

## 虚构案例

固定 JSON 位于 assets/mock-data/cases.json；商户底表位于 mock_merchants.json。
所有案例 synthetic=true，名称和标识仅供演示，不表示真实客户。

| Case | 输入特点 | 最新版本结果 |
| --- | --- | --- |
| A | CN 个人，格式/校验位正确，签名日期完整 | AUTO_PASS |
| B | CN 个人，错误校验位 | NEED_USER_FIX |
| C | 缺签名 | NEED_USER_FIX |
| D | HK 注册实体、申报 CN；附上游冲突 issue | MANUAL_TRIAGE |
| E | SG 实体 UEN ROC 中含非法字母；基线尚无 SG，更新后覆盖 | NEED_USER_FIX |

D 的冲突 issue 是明确的上游接口测试数据，并非规则引擎从商户底表自动推理得出。
商户注册地差异本身不证明申报错误，WARNING 代表待复核。
E 更新前使用规格约定的未知法域长度兜底，schema=2 当前返回 MANUAL_TRIAGE，更新后新增 SG 格式规则阻断。
执行器不会把未知法域标记为已完成国家算法校验。
本轮只提供结构化 JSON，PDF/图片原件与 OCR 不在规则引擎范围。
