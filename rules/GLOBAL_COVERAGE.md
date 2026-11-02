# 全球官方来源规则覆盖清单

核对日期：2026-11-02。当前增强版本 rules_global_v4.json 为 22 法域、66 条主体/标识类型规则；13 条 CHECKSUM，53 条 FORMAT_ONLY。v3 文件保留为历史快照。

**范围是有官方出处的结构规则，不是每个国家税号所有法律条件的完整实现。**
已启用有官方公式依据的算法，清单见下方。HKID/NRIC 在此全球规则集中采用格式检查，不将非官方算法来源包装成官方规则。

不收集真实税号，不验证真实签发、主体归属或税籍；你可自行构造测试数据。测试文件中的字符串仅验证格式边界。

| 法域 | 个人标识类型 | 企业标识类型 | 官方来源 |
| --- | --- | --- | --- |
| CN | CN_ID | CN_LEGACY_TIN, CN_ENTITY_TIN | [来源 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/china-tin.pdf) |
| HK | HKID | HK_BR | [来源 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/hong-kong-tin.pdf) |
| SG | SG_NRIC, SG_FIN | SG_UEN_ROB, SG_UEN_ROC, SG_UEN_OTHER | [来源 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/singapore-tin.pdf) |
| US | US_EIN, US_SSN, US_ITIN | US_EIN | [来源 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/united-states-tin.pdf) / [来源 2](https://secure.ssa.gov/apps10/poms.nsf/lnx/0110201035) / [来源 3](https://www.irs.gov/irm/part21/irm_21-002-004r) |
| AU | AU_TFN, AU_ABN | AU_TFN, AU_ABN | [来源 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/australia-tin.pdf) |
| NZ | NZ_IRD | NZ_IRD | [来源 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/new-zealand-tin.pdf) |
| NL | NL_TIN | NL_TIN | [来源 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/netherlands-tin.pdf) |
| IE | IE_TRN | IE_TRN, IE_CHY | [来源 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/ireland-tin.pdf) |
| ZA | ZA_INCOME_TAX | ZA_INCOME_TAX | [来源 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/south-africa-tin.pdf) |
| PL | PL_NIP, PL_PESEL | PL_NIP | [来源 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/poland-tin.pdf) |
| GB | GB_UTR, GB_NINO | GB_UTR | [来源 1](https://www.gov.uk/find-utr-number) / [来源 2](https://www.gov.uk/hmrc-internal-manuals/national-insurance-manual/nim39110) |
| CA | CA_SIN | CA_BN, CA_TRUST | [来源 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/canada-tin.pdf) |
| DE | DE_IDNR, DE_WIDNR, DE_WIDNR_ACTIVITY | DE_WIDNR, DE_WIDNR_ACTIVITY | [来源 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/germany-tin.pdf) / [来源 2](https://www.bundesfinanzministerium.de/Web/DE/Service/FAQ_Glossar/Glossar/Functions/glossar.html?lv2=176982&lv3=419562) |
| FR | FR_SPI | FR_SIREN, FR_SIRET | [来源 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/france-tin.pdf) |
| JP | JP_MY_NUMBER | JP_CORPORATE | [来源 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/japan-tin.pdf) |
| IN | IN_PAN | IN_PAN | [来源 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/india-tin.pdf) |
| CH | CH_OASI | CH_UID | [来源 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/switzerland-tin.pdf) |
| KR | KR_RRN | KR_BRN, KR_CRN | [来源 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/korea-tin.pdf) |
| ES | ES_DNI, ES_NIE, ES_SPECIAL_NIF | ES_NIF | [来源 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/spain-tin.pdf) |
| SE | SE_PERSONNUMMER, SE_COORDINATION | SE_ORGNR | [来源 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/sweden-tin.pdf) |
| NO | NO_NATIONAL_ID, NO_D_NUMBER | NO_ORGNR | [来源 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/norway-tin.pdf) |
| DK | DK_CPR | DK_CVR, DK_SE | [来源 1](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/denmark-tin.pdf) |

## 实际检查深度

- 规则内记录 source_section、reviewed_on、verification_level、limitations，可逐项追溯；核对日期不是法规生效日期。
- FORMAT_ONLY 只覆盖所编码的长度、字符、前缀等结构约束。即使官方提到校验位，也不代表本引擎已经实现其算法。
- CN_ID 执行已有 GB 11643 校验位。其他正式算法未来有可靠依据再独立加入，不靠模型生成。
- 印度 PAN 区分个人 P 与实体状态字符，但不检查姓名首字母与主体名称相符。
- 瑞士允许保留官方展示格式中的点号；瑞典个人号码允许 + 分隔；不会对所有国家无差别剥离这些符号。
- 德国已补充 W-IdNr 核心号码与五位经济活动后缀形式（个人经济经营者/实体），依据德国财政部说明；旧地方税号仍未纳入。此类号码格式不能证明企业活动适用性或 VAT 注册。
- 不覆盖全部海外领地、例外类型、旧号码和最新过渡制度。意大利、巴西、墨西哥、台湾、澳门、阿联酋等不在本批执行范围，不能宣称已覆盖。
- 旧版 schema=1 仍保留历史长度兜底；schema=2 包括此全球版本，未覆盖法域返回 UNSUPPORTED_JURISDICTION WARNING；类型未覆盖返回 UNSUPPORTED_TIN_TYPE WARNING。
- 这些 WARNING 会导致 MANUAL_TRIAGE。Case E 更新前结果已从有限检查下的 AUTO_PASS 更正为 MANUAL_TRIAGE，新增 SG 规则后仍为 NEED_USER_FIX。

## 查询和发布

```bash
uv run python -m backend.cli.rule_engine coverage
uv run python -m backend.cli.rule_engine current
uv run python -m backend.cli.rule_engine register rules/rules_global_v4.json
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


## 已启用的官方计算方法

| 算子 | 适用类型 | 计算依据 |
| --- | --- | --- |
| MOD11_2 | CN_ID | GB 11643-1999，原有算子 |
| AU_ABN | 澳大利亚个人经营者/实体 ABN | https://abr.business.gov.au/Help/AbnFormat |
| NL_MOD11 | 荷兰个人/非自然人 TIN | https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/netherlands-tin.pdf Section II |
| PL_NIP | 波兰个人经营者/实体 NIP | https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/poland-tin.pdf Section II.2.2 |
| PL_PESEL | 波兰个人 PESEL | 同上 Section II.2.1，另检查编码日期与世纪月份映射 |
| NO_ORGNR | 挪威实体组织号，可含 MVA 后缀 | https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/norway-tin.pdf Section II |
| JP_CORPORATE | 日本法人番号 | https://www.houjin-bangou.nta.go.jp/documents/checkdigit.pdf |
| CA_SIN | 加拿大个人 SIN | https://publications.gc.ca/collections/collection_2012/servicecanada/SG5-58-2011-eng.pdf 印刷页 11 |
| ES_NIF_NIE | 西班牙 DNI 与 X/Y/Z NIE | https://www.interior.gob.es/opencms/es/servicios-al-ciudadano/tramites-y-gestiones/dni/calculo-del-digito-de-control-del-nif-nie/ |

算法来源与格式来源分开记录，algorithm_source_url 会随 tin_check 返回。
13 条指主体/标识类型选择器数量，不等于 13 种不同算法。

## 已加深的结构条件

- SSN：根据 SSA 排除 000、666、9xx 开头，组号 00 和序号 0000。来源：https://secure.ssa.gov/apps10/poms.nsf/lnx/0110201035 。不查询已撤销号码或是否签发。
- ITIN：第四/五位限制为 50-65、70-88、90-92、94-99。来源：https://www.irs.gov/irm/part21/irm_21-002-004r 。不依据数字推定续期或过期。
- 英国 NINO：保留 HMRC 禁用前缀和末字母 A-D 限制；不把临时行政编号当正式 NINO。
- PESEL：校验位之外检查真实日历日期与五个世纪的月份编码；不将其自动解释成与表单出生日期一致。

## 仍未覆盖的深度

TFN、IRD、德国个人号、法国 SPI/SIREN/SIRET、瑞士号、新加坡各类号码等目前仍以格式为主。
部分公开技术文档有版本或适用范围差异，不能把一个通用 Luhn/MOD11 算子无依据应用于所有类型。
法国 SIRET 特例、新西兰 IRD 2026 数值范围调整等未在本轮强行推定。
Reason A/B/C 的法域适用、协定税籍判断、TIN 强制签发条件还需要补充可执行的业务契约及官方条款，不能仅从“有/无 TIN”推导。
这里是当前已验证范围与待办清单，不代表完整全球税法覆盖。
