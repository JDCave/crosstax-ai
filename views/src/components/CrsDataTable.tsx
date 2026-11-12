import React from 'react';
import { Card, Table, Tag, Typography } from 'antd';
import type { AuditIssue, CRSFormData } from '../types/api';

interface FieldRow {
  key: string;
  field: string;
  label: string;
  value: string;
  issue?: AuditIssue;
}

const FIELD_LABELS: Record<keyof CRSFormData, string> = {
  holder_name: '持有人姓名 / 实体名',
  holder_dob: '出生日期 / 成立日期',
  incorporation_date: '成立日期',
  residence_address: '居住 / 营业地址',
  jurisdiction_code: '税收居民地区',
  holder_type: '持有人类型',
  tin_type: 'TIN 类型',
  tin: 'TIN 号码',
  has_no_tin: '声明无 TIN',
  tin_reason_code: '无 TIN 原因',
  tin_reason_explanation: '原因 B 解释',
  has_signature: '是否有签名',
  signing_date: '签署日期',
};

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'TRUE' : 'FALSE';
  return String(value);
}

/**
 * 抽取/提交的 CRS 表单数据表格。
 * 命中 issue 的字段按严重级别着色（BLOCKER 红 / WARNING 琥珀）。
 */
const CrsDataTable: React.FC<{ formData: CRSFormData; issues?: AuditIssue[] }> = ({
  formData,
  issues = [],
}) => {
  const rows: FieldRow[] = (Object.keys(FIELD_LABELS) as Array<keyof CRSFormData>)
    .filter((key) => formData[key] !== undefined && formData[key] !== null)
    .map((key) => ({
      key,
      field: key,
      label: FIELD_LABELS[key],
      value: formatValue(formData[key]),
      issue: issues.find((i) => i.field === key),
    }));

  return (
    <Card
      size="small"
      title="表单数据 · CRSFormData"
      extra={
        <Typography.Text type="secondary" style={{ fontSize: 11, fontFamily: 'monospace' }}>
          {rows.length} FIELDS
        </Typography.Text>
      }
      style={{ height: '100%' }}
    >
      <Table<FieldRow>
        dataSource={rows}
        pagination={false}
        size="small"
        rowKey="key"
        columns={[
          {
            title: '字段',
            dataIndex: 'field',
            width: '38%',
            render: (field: string, row) => (
              <div>
                <Typography.Text code style={{ fontSize: 11 }}>
                  {field}
                </Typography.Text>
                <div style={{ fontSize: 11, color: '#94a3b8' }}>{row.label}</div>
              </div>
            ),
          },
          {
            title: '值',
            dataIndex: 'value',
            render: (value: string, row) => {
              const color =
                row.issue?.severity === 'BLOCKER'
                  ? '#dc2626'
                  : row.issue?.severity === 'WARNING'
                    ? '#d97706'
                    : undefined;
              return (
                <Typography.Text
                  strong={!!row.issue}
                  style={{ fontFamily: 'monospace', fontSize: 12, color, wordBreak: 'break-all' }}
                >
                  {value}
                </Typography.Text>
              );
            },
          },
          {
            title: '状态',
            key: 'status',
            width: 90,
            render: (_, row) =>
              row.issue ? (
                <Tag color={row.issue.severity === 'BLOCKER' ? 'red' : 'orange'} style={{ fontSize: 10 }}>
                  {row.issue.severity}
                </Tag>
              ) : (
                <Tag color="green" style={{ fontSize: 10 }}>
                  OK
                </Tag>
              ),
          },
        ]}
      />
    </Card>
  );
};

export default CrsDataTable;
