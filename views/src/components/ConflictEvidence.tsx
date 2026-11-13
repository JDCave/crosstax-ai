import React from 'react';
import { Card, Empty, Progress, Tag, Typography } from 'antd';
import { WarningOutlined } from '@ant-design/icons';
import type { ValidationResponse } from '../types/api';

/**
 * 冲突证据链（WARNING / 上游 indicia）：
 * 展示冲突字段、说明与置信度进度条。
 */
const ConflictEvidence: React.FC<{ result: ValidationResponse }> = ({ result }) => {
  const warnings = result.issues.filter((i) => i.severity === 'WARNING');
  const upstreamSet = new Set(
    result.issue_origins.filter((o) => o.source === 'UPSTREAM').map((o) => o.issue_index),
  );

  if (warnings.length === 0) {
    return (
      <Card
        size="small"
        title={
          <span>
            <WarningOutlined /> 冲突证据链 · Indicia Conflicts
          </span>
        }
        extra={<Tag color="green">0 CONFLICTS</Tag>}
        style={{ height: '100%' }}
      >
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="未检测到跨源税籍指示冲突"
          style={{ margin: '24px 0' }}
        />
      </Card>
    );
  }

  return (
    <Card
      size="small"
      title={
        <span>
          <WarningOutlined /> 冲突证据链 · Indicia Conflicts
        </span>
      }
      extra={<Tag color="orange">WARNING ×{warnings.length}</Tag>}
      style={{ height: '100%' }}
    >
      {warnings.map((warning) => {
        const globalIndex = result.issues.indexOf(warning);
        const fromUpstream = upstreamSet.has(globalIndex);
        return (
          <div
            key={globalIndex}
            style={{
              border: '1px solid #f59e0b',
              borderLeft: '3px solid #d97706',
              padding: 12,
              marginBottom: 8,
              background: '#fffbeb',
              borderRadius: 2,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <Tag color="orange" style={{ fontFamily: 'monospace', fontSize: 10 }}>
                {warning.code}
              </Tag>
              <Typography.Text strong style={{ fontSize: 12 }}>
                {warning.field ?? 'document'}
              </Typography.Text>
              <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                <Typography.Text type="secondary" style={{ fontSize: 11, fontFamily: 'monospace' }}>
                  confidence: {warning.confidence.toFixed(2)}
                </Typography.Text>
                <Progress
                  percent={Math.round(warning.confidence * 100)}
                  size="small"
                  style={{ width: 72, margin: 0 }}
                  strokeColor="#d97706"
                  showInfo={false}
                />
              </span>
            </div>
            <Typography.Paragraph style={{ fontSize: 12, marginBottom: 4 }}>
              {warning.message}
            </Typography.Paragraph>
            <Typography.Text type="secondary" style={{ fontSize: 11 }}>
              来源：{fromUpstream ? '上游跨源研判（UPSTREAM）' : '规则引擎（RULE_ENGINE）'}
            </Typography.Text>
          </div>
        );
      })}
    </Card>
  );
};

export default ConflictEvidence;
