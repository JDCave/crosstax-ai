# 全球官方来源规则覆盖清单

核对日期：2026-11-02。当前为 22 法域、62 条主体/标识类型规则。

**范围是有官方出处的结构规则，不是每个国家税号所有法律条件的完整实现。**
新增规则均为 FORMAT_ONLY；保留有标准依据的 CN_ID 校验位。HKID/NRIC 在此全球规则集中采用格式检查，不将非官方算法来源包装成官方规则。

不收集真实税号，不验证真实签发、主体归属或税籍；你可自行构造测试数据。测试文件中的字符串仅验证格式边界。

| 法域 | 个人标识类型 | 企业标识类型 | 官方来源 |
| --- | --- | --- | --- |
| CN | CN_ID | CN_LEGACY_TIN, CN_ENTITY_TIN | [官方资料 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/china-tin.pdf) |
| HK | HKID | HK_BR | [官方资料 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/hong-kong-tin.pdf) |
| SG | SG_NRIC, SG_FIN | SG_UEN_ROB, SG_UEN_ROC, SG_UEN_OTHER | [官方资料 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/singapore-tin.pdf) |
| US | US_EIN, US_SSN, US_ITIN | US_EIN | [官方资料 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/united-states-tin.pdf) |
| AU | AU_TFN, AU_ABN | AU_TFN, AU_ABN | [官方资料 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/australia-tin.pdf) |
| NZ | NZ_IRD | NZ_IRD | [官方资料 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/new-zealand-tin.pdf) |
| NL | NL_TIN | NL_TIN | [官方资料 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/netherlands-tin.pdf) |
| IE | IE_TRN | IE_TRN, IE_CHY | [官方资料 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/ireland-tin.pdf) |
| ZA | ZA_INCOME_TAX | ZA_INCOME_TAX | [官方资料 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/south-africa-tin.pdf) |
| PL | PL_NIP, PL_PESEL | PL_NIP | [官方资料 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/poland-tin.pdf) |
| GB | GB_UTR, GB_NINO | GB_UTR | [官方资料 1](https://www.gov.uk/find-utr-number) / [官方资料 2](https://www.gov.uk/hmrc-internal-manuals/national-insurance-manual/nim39110) |
| CA | CA_SIN | CA_BN, CA_TRUST | [官方资料 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/canada-tin.pdf) |
| DE | DE_IDNR | 未覆盖 | [官方资料 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/germany-tin.pdf) |
| FR | FR_SPI | FR_SIREN, FR_SIRET | [官方资料 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/france-tin.pdf) |
| JP | JP_MY_NUMBER | JP_CORPORATE | [官方资料 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/japan-tin.pdf) |
| IN | IN_PAN | IN_PAN | [官方资料 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/india-tin.pdf) |
| CH | CH_OASI | CH_UID | [官方资料 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/switzerland-tin.pdf) |
| KR | KR_RRN | KR_BRN, KR_CRN | [官方资料 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/korea-tin.pdf) |
| ES | ES_DNI, ES_NIE, ES_SPECIAL_NIF | ES_NIF | [官方资料 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/spain-tin.pdf) |
| SE | SE_PERSONNUMMER, SE_COORDINATION | SE_ORGNR | [官方资料 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/sweden-tin.pdf) |
| NO | NO_NATIONAL_ID, NO_D_NUMBER | NO_ORGNR | [官方资料 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/norway-tin.pdf) |
| DK | DK_CPR | DK_CVR, DK_SE | [官方资料 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/denmark-tin.pdf) |

## 实际检查深度

- 规则内记录 source_section、reviewed_on、verification_level、limitations，可逐项追溯；核对日期不是法规生效日期。
- FORMAT_ONLY 只覆盖所编码的长度、字符、前缀等结构约束。即使官方提到校验位，也不代表本引擎已经实现其算法。
- CN_ID 执行已有 GB 11643 校验位。其他正式算法未来有可靠依据再独立加入，不靠模型生成。
- 印度 PAN 区分个人 P 与实体状态字符，但不检查姓名首字母与主体名称相符。
- 瑞士允许保留官方展示格式中的点号；瑞典个人号码允许 + 分隔；不会对所有国家无差别剥离这些符号。
- 德国只覆盖个人 IdNr，企业 W-IdNr 与旧税号尚未纳入。OECD 历史文档可能滞后，不把未覆盖解释为不签发。
- 不覆盖全部海外领地、例外类型、旧号码和最新过渡制度。意大利、巴西、墨西哥、台湾、澳门、阿联酋等不在本批执行范围，不能宣称已覆盖。
- 旧版 schema=1 仍保留历史长度兜底；schema=2 包括此全球版本，未覆盖法域返回 UNSUPPORTED_JURISDICTION WARNING；类型未覆盖返回 UNSUPPORTED_TIN_TYPE WARNING。
- 这些 WARNING 会导致 MANUAL_TRIAGE。Case E 更新前结果已从有限检查下的 AUTO_PASS 更正为 MANUAL_TRIAGE，新增 SG 规则后仍为 NEED_USER_FIX。

## 查询和发布

```bash
uv run python -m backend.cli.rule_engine coverage
uv run python -m backend.cli.rule_engine current
uv run python -m backend.cli.rule_engine register rules/rules_global_v3.json
# 根据上一条返回的版本号审批，然后使用当前 revision 激活。
uv run python -m backend.cli.rule_engine approve VERSION_ID --report /path/to/review.json
uv run python -m backend.cli.rule_engine activate VERSION_ID --revision CURRENT_REVISION
```

本地 devdb 已激活该完整快照。旧的 demo_cases --install 仍是安装原三法域竞赛快照，会把活动指针切回该版本；仅运行 demo_cases 不修改数据库。

## 结果字段

ValidationResult.tin_check 包含 status、verification_level、rule_id、source_url。
PASSED 表示所声明的检查等级通过；NOT_COVERED 不得显示成“官方验证通过”；NOT_APPLICABLE 用于 has_no_tin 豁免路径。
格式通过仍按现有裁决规则允许 AUTO_PASS，但前端必须展示 FORMAT_ONLY，不能声称已完成全部税法规则或号码真实性核验。

## 后续更新

官方来源变化后，维护结构化规则并创建新版本；不在审核请求中调用网页或大模型。
来源文档未提供、含糊或与新公告冲突的规则暂不启用。当前 reviewed_on 表示本次人工核对，而不是已经部署全球自动法规解释服务。
