# CrossTax AI — 数据模型规格

> **版本：** v1.0 | **日期：** 2026-10-25  
> **来源：** 从 `design/architecture.md` §2.2.1 和 §3.2 提取  
> **用途：** 前后端共享的数据契约，定义核心数据结构的字段、类型和约束

---

## 1. 核心数据模型

### 1.1 CRSFormData — Vision Agent 抽取的结构化输出

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `holder_name` | string | 是 | 账户持有人姓名/实体名 |
| `holder_dob` | string (YYYY-MM-DD) | 是 | 出生日期 / 成立日 |
| `residence_address` | string | 是 | 现居住地/常设地址 |
| `jurisdiction_code` | string (ISO 2字码) | 是 | 申报国家代码，如 CN/HK/SG |
| `tin` | string \| null | 否 | 纳税人识别号 |
| `has_no_tin` | boolean | 是 | 是否无 TIN 标记 |
| `tin_reason_code` | "A" \| "B" \| "C" \| null | 条件必填 | 豁免理由代码（has_no_tin=true 时必填） |
| `tin_reason_explanation` | string \| null | 条件必填 | 理由解释（Reason B 时必填，≥5 字符） |
| `has_signature` | boolean | 是 | 是否有签名 |
| `signing_date` | string (YYYY-MM-DD) \| null | 条件必填 | 签署日期（has_signature=true 时必填） |

**JSON 示例：**
```json
{
  "holder_name": "ACME Trading Ltd",
  "holder_dob": "2015-03-15",
  "residence_address": "Unit 12, 88 Queen's Road, HK",
  "jurisdiction_code": "HK",
  "tin": "A123456(7)",
  "has_no_tin": false,
  "tin_reason_code": null,
  "tin_reason_explanation": null,
  "has_signature": true,
  "signing_date": "2026-09-01"
}
```

---

### 1.2 AuditIssue — 单条审核问题

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `code` | string | 是 | 问题代码，如 `INVALID_TIN`、`NO_SIGNATURE` |
| `severity` | "BLOCKER" \| "WARNING" | 是 | 严重级别 |
| `field` | string \| null | 否 | 关联的表单字段名 |
| `message` | string | 是 | 通俗描述（面向用户） |
| `confidence` | float (0.0-1.0) | 是 | 判定置信度 |

**问题代码枚举：**

| 代码 | 严重级别 | 触发条件 |
|------|----------|----------|
| `NO_SIGNATURE` | BLOCKER | `has_signature == false` |
| `INVALID_DATE` | BLOCKER | 签署日期缺失或无效 |
| `INVALID_TIN` | BLOCKER | TIN 校验位算法失败 |
| `MISSING_REASON` | BLOCKER | `has_no_tin=true` 但未选择 Reason A/B/C |
| `INDICIA_CONFLICT` | WARNING | 跨源税籍指示冲突（场景 1/2/3） |

**JSON 示例：**
```json
{
  "code": "INVALID_TIN",
  "severity": "BLOCKER",
  "field": "tin",
  "message": "TIN 校验位不匹配，预期值 7，实际值 8",
  "confidence": 1.0
}
```

---

### 1.3 AuditSession — 审核会话（审计留痕最小单元）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `session_id` | string (UUID) | 是 | 会话唯一标识 |
| `merchant_id` | string | 是 | 商户 ID |
| `file_hash` | string (SHA-256) | 是 | 原始文件哈希 |
| `rule_version_id` | string | 是 | 规则版本号（内容哈希） |
| `form_data` | CRSFormData | 是 | 抽取的结构化数据 |
| `form_issues` | AuditIssue[] | 是 | 形式完备性问题列表 |
| `indicia_issues` | AuditIssue[] | 是 | 跨源冲突问题列表 |
| `verdict` | string | 是 | 裁决结果 |
| `timestamp` | datetime (ISO 8601) | 是 | 裁决时间戳 |

**裁决结果枚举：**

| 值 | 条件 | 业务动作 |
|----|------|----------|
| `AUTO_PASS` | 无 BLOCKER + 无 WARNING | 自动放行 |
| `NEED_USER_FIX` | 存在任意 BLOCKER | 暂缓，生成修复卡片 |
| `MANUAL_TRIAGE` | 无 BLOCKER + 存在 WARNING | 推送合规官 |

---

### 1.4 PipelineStep — 流水线步骤状态（WebSocket 推送）

| 字段 | 类型 | 说明 |
|------|------|------|
| `step` | string | 步骤标识 |
| `status` | "wait" \| "process" \| "finish" \| "error" | 步骤状态 |
| `label` | string | 步骤显示名称 |
| `message` | string | 步骤描述/结果 |

---

## 2. 商户底表（Mock 数据）

| 字段 | 类型 | 说明 |
|------|------|------|
| `merchant_id` | string | 商户唯一标识 |
| `kyc_legal_name` | string | KYC 法定注册主体名称 |
| `incorporation_jurisdiction` | string (ISO 2字码) | 注册成立地 |
| `primary_operating_country` | string (ISO 2字码) | 主要运营国家 |
| `bank_settlement_country` | string (ISO 2字码) | 银行结算国家 |
| `phone_country_code` | string | 联系人电话区号 |

**数据来源：** `assets/mock-data/mock_merchants.json`

---

## 3. 规则配置结构

| 字段 | 类型 | 说明 |
|------|------|------|
| `{jurisdiction_code}` | object | 法域代码为 key |
| `.regex` | string | TIN 正则表达式 |
| `.algorithm` | "MOD11_2" \| "HKID_WEIGHT" \| "NRIC_WEIGHT" \| "REGEX_ONLY" | 校验算法 |

**数据来源：** `rules/rules_v1_base.json`、`rules/rules_v2_patch.json`

---

## 4. 数据流

```
CRSFormData → FormCompletenessChecker → form_issues[]
                                        ↘
CRSFormData → TINValidatorEngine    → tin_issues[]   → VerdictResolver → verdict
                                        ↗
CRSFormData → IndiciaReasoningAgent → indicia_issues[]
              (+ merchant data)
```

---

## 5. 参考

- 架构设计：[`design/architecture.md`](../design/architecture.md)
- PRD：[`specs/prd.md`](./prd.md)
- ADR 索引：[`specs/adr/`](./adr/)
