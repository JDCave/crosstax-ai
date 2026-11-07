# CRS 官方表格模板

来源：香港税务局（IRD）官方空白示范表格，供金融机构参考和采用。
下载日期：2026-11-04。PDF 保持官网原文件，未填写任何个人或企业资料。

| 文件 | 用途 | 官方下载地址 |
| --- | --- | --- |
| [crs-individual-ird.pdf](crs-individual-ird.pdf) | 个人账户持有人自我证明表格 | https://www.ird.gov.hk/eng/pdf/2016/scf_ind.pdf |
| [crs-entity-ird.pdf](crs-entity-ird.pdf) | 实体账户持有人自我证明表格 | https://www.ird.gov.hk/eng/pdf/2016/scf_entity.pdf |
| [crs-controlling-person-ird.pdf](crs-controlling-person-ird.pdf) | 控权人自我证明表格。实体版 Part 3 明文要求 Passive NFE 另附此表 | https://www.ird.gov.hk/eng/pdf/2016/scf_cp.pdf |
| [crs-terms-ird.pdf](crs-terms-ird.pdf) | 表格术语的定义与解释（FI / Active NFE / Passive NFE / 控权人 / 税收居民身份等） | https://www.ird.gov.hk/eng/pdf/2016/terms.pdf |

官方来源页面：https://www.ird.gov.hk/eng/tax/aeoi/self_cert.htm

四份 PDF 的 SHA-256 已于 2026-11-05 从上述官方地址重新下载并逐字节比对，全部一致：

| 文件 | SHA-256 | 字节数 |
| --- | --- | --- |
| crs-individual-ird.pdf | `2a1294d624f9fdcfdfb75c57e3cbc37898587abe9449973ba084b1f06a6d444c` | 419,045 |
| crs-entity-ird.pdf | `4e4fcd4679bf0c10e35b143ad9447639be44d3f76ce8e970e48c415fb5966263` | 426,104 |
| crs-controlling-person-ird.pdf | `be5bd468cf2afd89fa821bbfe00093066c7b85ef8374e0c76907bb6f278c53c5` | 457,162 |
| crs-terms-ird.pdf | `d535aa4c144fc515dd04ff151e6753e0c357132ec671429447a55cfdc6c168ea` | 459,498 |

复现：`sha256sum assets/crs-templates/*.pdf`。四份均为 AES-128 加密（空用户密码）的 Tagged PDF，
`/MarkInfo /Marked true`，含 `/StructTreeRoot` 表格结构树。

用于项目表单、数据提取及演示的模板参考；表格字段不代表当前规则引擎已全部支持。
个人版与实体版两份表格均支持多个税收居民地区及对应 TIN；实体版还包含实体分类，
Passive NFE 的控权人信息须另附控权人表格填写，术语以术语表为准。

当前实现已支持最多 20 个不同税籍；实体不再强制提供成立日期。上游新契约规划仍需与当前实现逐项对齐。

## API 请求示例

队友接入请先阅读 [CRS 表格校验接口说明](API_INTEGRATION.md)，包含两份完整请求、字段映射、调用方式和返回结果说明。

- [个人版请求](crs-individual-request.json)
- [实体版请求](crs-entity-request.json)

用于 `POST /api/v1/rule-engine/validate`，姓名、地址和号码均为虚构测试数据，不代表真实签发记录。
示例业务日期为 2026-11-04，实际调用时由主后端传入业务日期。

另提供 [多税籍及 AI 补正请求](crs-multi-residence-request.json)，用于演示一次校验多个地区和请求补正建议。
当前实体无需出生／成立日期，实体 PDF 不含成立日期，不应补造。
多税籍最多 20 个不同地区，完整范围和 AI 降级机制见上述接入文档。

从仓库根目录调用示例：

```bash
curl -X POST http://localhost:8000/api/v1/rule-engine/validate \
  -H 'Content-Type: application/json' \
  --data-binary @assets/crs-templates/crs-individual-request.json
```

完整接口说明见 [规则引擎 API 文档](../../backend/api/RULE_ENGINE_API.md)。
