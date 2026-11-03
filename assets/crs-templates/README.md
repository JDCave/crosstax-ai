# CRS 官方表格模板

来源：香港税务局（IRD）官方空白示范表格，供金融机构参考和采用。
下载日期：2026-11-04。PDF 保持官网原文件，未填写任何个人或企业资料。

| 文件 | 用途 | 官方下载地址 |
| --- | --- | --- |
| [crs-individual-ird.pdf](crs-individual-ird.pdf) | 个人账户持有人自我证明表格 | https://www.ird.gov.hk/eng/pdf/2016/scf_ind.pdf |
| [crs-entity-ird.pdf](crs-entity-ird.pdf) | 实体账户持有人自我证明表格 | https://www.ird.gov.hk/eng/pdf/2016/scf_entity.pdf |

官方来源页面：https://www.ird.gov.hk/eng/tax/aeoi/self_cert.htm

用于项目表单、数据提取及演示的模板参考；表格字段不代表当前规则引擎已全部支持。
两份表格均支持多个税收居民地区及对应 TIN；实体版还包含实体分类和控权人信息。

## API 请求示例

- [个人版请求](crs-individual-request.json)
- [实体版请求](crs-entity-request.json)

用于 `POST /api/v1/rule-engine/validate`，姓名、地址和号码均为虚构测试数据，不代表真实签发记录。
示例业务日期为 2026-11-04，实际调用时由主后端传入业务日期。

`jurisdiction_code` 表示税收居民地区，不能直接用地址或注册地代替。
当前接口一次只支持一个税收居民地区及 TIN，不支持实体分类、控权人等额外字段。
实体请求中的 `holder_dob` 表示成立日期，是当前接口必填字段；实体版 PDF 不含该字段，
示例假设由上游其他资料补充，不能从表格中凭空生成。
当前香港规则只检查号码格式，不验证签发真实性或归属。

从仓库根目录调用示例：

```bash
curl -X POST http://localhost:8000/api/v1/rule-engine/validate \
  -H 'Content-Type: application/json' \
  --data-binary @assets/crs-templates/crs-individual-request.json
```

完整接口说明见 [规则引擎 API 文档](../../backend/api/RULE_ENGINE_API.md)。
