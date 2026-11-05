# CRS 表格校验接口：队友接入说明

主后端从表格或其他资料提取结构化数据后，调用本接口，同步获取校验结果。
本接口不负责读取 PDF、OCR、调用大模型提取信息，也不保存表单或结果。

## 调用地址

```http
POST /api/v1/rule-engine/validate
Content-Type: application/json
```

本地 Base URL：`http://localhost:8000`。其他机器调用时替换为规则引擎服务的可达地址。
服务运行后可访问 `http://localhost:8000/docs` 查看交互文档。
需要先加载 `rules/` 下的活动规则（ADR-003：JSON 文件 + 内存原子替换，规则不经数据库），否则返回 503 `NO_ACTIVE_RULES`。
当前接口面向内部服务，未新增认证；主后端负责用户权限及结果保存。

## 个人版请求

对应 [个人版官方 PDF](crs-individual-ird.pdf)，可直接使用 [请求 JSON](crs-individual-request.json)。

```json
{
  "form_data": {
    "holder_name": "CHAN DEMO",
    "holder_dob": "1990-05-20",
    "residence_address": "Flat 1, Demo Building, Demo Street, Hong Kong",
    "jurisdiction_code": "HK",
    "holder_type": "INDIVIDUAL",
    "tin_type": "HKID",
    "tin": "A123456(3)",
    "has_no_tin": false,
    "tin_reason_code": null,
    "tin_reason_explanation": null,
    "has_signature": true,
    "signing_date": "2026-11-04"
  },
  "policy": {
    "today": "2026-11-04"
  },
  "indicia_issues": []
}
```

## 实体版请求

对应 [实体版官方 PDF](crs-entity-ird.pdf)，可直接使用 [请求 JSON](crs-entity-request.json)。

```json
{
  "form_data": {
    "holder_name": "DEMO CROSS BORDER LIMITED",
    "holder_dob": "2020-06-15",
    "residence_address": "Room 101, Demo Commercial Building, Hong Kong",
    "jurisdiction_code": "HK",
    "holder_type": "ENTITY",
    "tin_type": "HK_BR",
    "tin": "12345678",
    "has_no_tin": false,
    "tin_reason_code": null,
    "tin_reason_explanation": null,
    "has_signature": true,
    "signing_date": "2026-11-04"
  },
  "policy": {
    "today": "2026-11-04"
  },
  "indicia_issues": []
}
```

以上姓名、地址和号码均为虚构测试数据，不代表真实签发记录。
实体成立日期为示例补充资料，不是从该 PDF 提取的字段。

## 字段与表格映射

| API 字段 | 个人表格来源 | 实体表格来源及注意事项 |
| --- | --- | --- |
| form_data.holder_name | Part 1 姓名，合并姓名各部分 | Part 1 实体或分支机构法定名称 |
| form_data.holder_dob | Part 1 出生日期 | 当前接口必填，表示成立日期；PDF 没有此字段，需上游其他资料补充，不能编造 |
| form_data.residence_address | Part 1 当前居住地址，合并为字符串 | Part 1 当前营业地址，合并为字符串 |
| form_data.jurisdiction_code | Part 2 税收居民地区 | Part 4 税收居民地区；不是注册地或地址所在地区 |
| form_data.holder_type | 固定 INDIVIDUAL | 固定 ENTITY；不是表格中的 Active/Passive NFE 分类 |
| form_data.tin_type | 香港个人示例使用 HKID | 香港实体示例使用 HK_BR；其他地区按规则支持的类型填写 |
| form_data.tin | 对应税收居民地区的 TIN | 对应税收居民地区的 TIN；香港实体使用商业登记号码 |
| form_data.has_no_tin | 是否声明无 TIN | 同个人；使用 JSON true/false |
| form_data.tin_reason_code | 无 TIN 原因 A/B/C | 同个人；有 TIN 时省略或 null |
| form_data.tin_reason_explanation | Reason B 的解释 | 同个人；Reason B 去除首尾空白后至少 5 字符 |
| form_data.has_signature | Part 3 是否有签名 | Part 5 是否有签名；由上游判断，本接口不验证笔迹或签名真伪 |
| form_data.signing_date | Part 3 签署日期 | Part 5 签署日期 |
| policy.today | 主后端提供业务日期 | 同个人；不是 PDF 提取字段 |
| indicia_issues | 可选，上游跨源核查问题 | 同个人；无问题可省略或传空数组 |

日期统一转换为 `YYYY-MM-DD`，PDF 上的 `dd/mm/yyyy` 不能原样传入。
签署日期不得晚于 policy.today；示例业务日期为 2026-11-04，实际调用由主后端明确传入。
TIN 必须为字符串，保留前导零；引擎会移除空白、括号和连字符并转换大写。
顶层和 form_data 不接受未知字段。完整长度、类型和 policy 可选字段以服务运行后
`http://localhost:8000/docs` 生成的实时接口文档为准——该文档由代码生成，不会与本文件漂移。

无 TIN 时传 `has_no_tin: true`、`tin: null`，并填写 A/B/C；B 还须解释。
当前只检查豁免声明完整性，适用性需要人工复核，不会凭无 TIN 声明自动通过。

## 调用示例

在仓库根目录执行个人样例：

```bash
curl -X POST http://localhost:8000/api/v1/rule-engine/validate \
  -H 'Content-Type: application/json' \
  --data-binary @assets/crs-templates/crs-individual-request.json
```

实体样例：

```bash
curl -X POST http://localhost:8000/api/v1/rule-engine/validate \
  -H 'Content-Type: application/json' \
  --data-binary @assets/crs-templates/crs-entity-request.json
```

## 返回结果

接口直接返回 JSON，不包裹 result，也不需要 session_id。成功响应字段如下：

| 字段 | 含义 |
| --- | --- |
| verdict | AUTO_PASS、NEED_USER_FIX 或 MANUAL_TRIAGE |
| issues | 问题数组；每项有 code、severity、field、message、confidence |
| rule_version_id | 本次规则内容哈希 |
| rule_revision | 本次活动规则修订号 |
| checks | TIN 执行状态、校验深度、官方来源、已执行及未执行检查；可为 null |
| execution | 引擎构建指纹、输入指纹、执行策略；可为 null |

两份样例在当前 global v4 规则下、没有上游问题时，均预期返回
`verdict: AUTO_PASS`、`issues: []`，checks 的 status 为 PASSED、
verification_level 为 FORMAT_ONLY。它们只通过当前已实现的检查，不代表税收居民身份、
号码签发或归属、整张官方表格的全部要求均已核实。规则版本和指纹以实际响应为准。

| verdict | 主后端处理建议 |
| --- | --- |
| AUTO_PASS | 当前检查无问题，记录本次结果 |
| NEED_USER_FIX | 存在 BLOCKER，展示 issues 并要求用户更正 |
| MANUAL_TRIAGE | 无 BLOCKER 但存在 WARNING，进入人工复核 |

正常业务裁决均为 HTTP 200，必须读取 verdict，不能仅按 HTTP 状态判定通过。
BLOCKER 优先于 WARNING；上游 indicia_issues 也参与裁决。

## 错误处理

错误结构示例：

```json
{"code": "VALIDATION_ERROR", "message": "Invalid request JSON or field values"}
```

| HTTP | code | 处理 |
| --- | --- | --- |
| 413 | REQUEST_TOO_LARGE | 请求体超过 1 MiB，缩小请求 |
| 422 | VALIDATION_ERROR | 检查 JSON、未知字段、字段类型和日期策略 |
| 503 | NO_ACTIVE_RULES | 联系规则引擎维护者发布活动规则 |
| 503 | RULE_ENGINE_UNAVAILABLE | 规则文件不可读或引擎未就绪，按主后端策略重试 |
| 500 | INTERNAL_ERROR | 记录错误并联系维护者 |

表单缺签、TIN 格式错误等业务问题通常是 HTTP 200 + NEED_USER_FIX，区别于请求结构错误。

## 当前接入边界

- 一次请求只支持一个税收居民地区及一个 TIN；两份 PDF 均支持多地区，当前接口不能给出多地区整表的汇总裁决。
- 实体分类、控权人、邮寄地址、出生地、授权签署人等完整表格信息尚未纳入此请求契约，不能直接增加字段提交。
- 实体成立日期缺失时，当前契约无法仅靠这份 PDF 构造完整请求，应由上游补充资料；不要填写虚构日期用于真实业务。
- 当前香港规则为格式校验，不检查校验位、真实性或归属；规则未覆盖的地区或类型转人工复核。
- 每次调用读取当时的活动规则，重试可能因规则更新返回不同结果；主后端应保存请求与完整响应作为本次审核依据。

本节描述的是**当前已发布契约**的状态。其中多税收居民地、实体分类、控权人、出生地四项已完成契约层设计
（`tax_residencies[]` 重复组及相应字段位，见 `.specify/features/001-crs-contract/`），但**尚无实现**。
在实现落地前本节每一条仍然成立：不得依据设计文档提前提交新字段，接口对未知字段零容忍。
