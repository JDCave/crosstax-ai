import React from 'react';
import { Alert, Card, Descriptions, Table, Tag, Tooltip, Typography } from 'antd';
import { CheckCircleOutlined, InfoCircleOutlined } from '@ant-design/icons';
import type { CheckItem, CheckItemStatus, TinCheckStatus, ValidationResponse } from '../types/api';

const CHECK_STATUS_TAG: Record<CheckItemStatus, { color: string; text: string }> = {
  PASSED: { color: 'green', text: '✓ PASS' },
  FAILED: { color: 'red', text: '✗ FAIL' },
  REVIEW_REQUIRED: { color: 'orange', text: '⚠ REVIEW' },
  NOT_APPLICABLE: { color: 'default', text: '— N/A' },
};

const TIN_STATUS_TAG: Record<TinCheckStatus, { color: string; text: string }> = {
  PASSED: { color: 'green', text: 'PASSED' },
  FAILED: { color: 'red', text: 'FAILED' },
  NOT_COVERED: { color: 'orange', text: 'NOT_COVERED' },
  NOT_APPLICABLE: { color: 'default', text: 'NOT_APPLICABLE' },
};

/**
 * 校验明细：逐项检查（check_items）+ TIN 检查摘要 + 审查范围声明
 */
const ValidationChecks: React.FC<{ result: ValidationResponse }> = ({ result }) => {
  const tin = result.checks;

  return (
    <Card
      size="small"
      title={
        <span>
          <CheckCircleOutlined /> 校验明细 · Validation Checks
        </span>
      }
      extra={
        tin && (
          <Tag color={TIN_STATUS_TAG[tin.status].color} style={{ fontFamily: 'monospace', fontSize: 10 }}>
            TIN: {TIN_STATUS_TAG[tin.status].text} · {tin.verification_level}
          </Tag>
        )
      }
    >
      {result.check_items.length > 0 && (
        <Table<CheckItem>
          dataSource={result.check_items}
          pagination={false}
          size="small"
          rowKey="check_id"
          style={{ marginBottom: 12 }}
          columns={[
            {
              title: '检查项',
              dataIndex: 'check_id',
              render: (id: string, row) => (
                <div>
                  <Typography.Text code style={{ fontSize: 11 }}>
                    {id}
                  </Typography.Text>
                  <div style={{ fontSize: 11, color: '#94a3b8' }}>{row.field}</div>
                </div>
              ),
            },
            {
              title: '结果',
              dataIndex: 'status',
              width: 120,
              render: (status: CheckItemStatus) => (
                <Tag color={CHECK_STATUS_TAG[status].color}>{CHECK_STATUS_TAG[status].text}</Tag>
              ),
            },
          ]}
        />
      )}

      {tin && (
        <Descriptions size="small" column={2} bordered style={{ marginBottom: 12 }}>
          <Descriptions.Item label="TIN 执行状态">
            <Tag color={TIN_STATUS_TAG[tin.status].color}>{TIN_STATUS_TAG[tin.status].text}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="校验深度">
            <Tooltip title="FORMAT_ONLY 表示仅格式校验，不代表号码签发真实性或归属已核实">
              <Typography.Text style={{ fontSize: 12 }}>
                {tin.verification_level} <InfoCircleOutlined style={{ color: '#94a3b8' }} />
              </Typography.Text>
            </Tooltip>
          </Descriptions.Item>
          {tin.rule_id && (
            <Descriptions.Item label="命中规则">
              <Typography.Text code style={{ fontSize: 11 }}>
                {tin.rule_id}
              </Typography.Text>
            </Descriptions.Item>
          )}
          {tin.reason_code && (
            <Descriptions.Item label="原因码">
              <Typography.Text code style={{ fontSize: 11 }}>
                {tin.reason_code}
              </Typography.Text>
            </Descriptions.Item>
          )}
          {tin.checks_performed.length > 0 && (
            <Descriptions.Item label="已执行检查" span={2}>
              <Typography.Text style={{ fontSize: 11, fontFamily: 'monospace' }}>
                {tin.checks_performed.join(', ')}
              </Typography.Text>
            </Descriptions.Item>
          )}
          {tin.checks_not_performed.length > 0 && (
            <Descriptions.Item label="未执行检查" span={2}>
              <Typography.Text type="secondary" style={{ fontSize: 11, fontFamily: 'monospace' }}>
                {tin.checks_not_performed.join(', ')}
              </Typography.Text>
            </Descriptions.Item>
          )}
        </Descriptions>
      )}

      <Alert
        style={{ marginTop: 4 }}
        type="info"
        showIcon
        message={
          <Typography.Text style={{ fontSize: 11 }}>{result.review_scope.statement}</Typography.Text>
        }
      />
    </Card>
  );
};

export default ValidationChecks;
