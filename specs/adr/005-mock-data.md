# ADR-005: Mock 数据替代真实对接

## 状态
已采纳 (2026-10-22)

## 背景
竞赛环境无真实商户系统，需模拟 KYC/CRM 数据。

## 决策
采用 Mock 数据文件（JSON）替代真实系统对接。

## 否决方案
- **对接真实 KYC/CRM API**：无权限、无数据、无时间

## 理由
- 竞赛场景无需真实数据
- Mock 数据可精确控制 5 个典型 Case 的覆盖范围
- 减少外部依赖，演示稳定可控

## 后果
- Mock 商户底表：`assets/mock-data/mock_merchants.json`
- 5 个 CRS 样本文件：`assets/mock-data/samples/`
- 需与合规专家共同设计 Case 数据，确保覆盖三态裁决
