import React from 'react';
import { Alert, Card, Collapse, Empty, Tag, Typography } from 'antd';
import { ToolOutlined } from '@ant-design/icons';
import type { ExplanationCard, ValidationResponse } from '../types/api';

/**
 * 修复建议卡片（Collapse）：
 * 优先展示后端 explanation_cards（含规则/Agent 补正动作）；
 * 无卡片时按 issue 列表降级展示。
 */
const RemediationCards: React.FC<{ result: ValidationResponse }> = ({ result }) => {
  const blockerIndexes = new Set(
    result.issues
      .map((issue, index) => ({ issue, index }))
      .filter(({ issue }) => issue.severity === 'BLOCKER')
      .map(({ index }) => index),
  );

  const cards: ExplanationCard[] = result.explanation_cards.filter((c) =>
    blockerIndexes.has(c.issue_index),
  );

  const blockers = result.issues
    .map((issue, index) => ({ issue, index }))
    .filter(({ issue }) => issue.severity === 'BLOCKER');

  return (
    <Card
      size="small"
      title={
        <span>
          <ToolOutlined /> 修复建议 · Remediation
        </span>
      }
      extra={
        blockers.length > 0 ? (
          <Tag color="red">BLOCKER ×{blockers.length}</Tag>
        ) : (
          <Tag color="green">无阻断项</Tag>
        )
      }
      style={{ height: '100%' }}
    >
      {blockers.length === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="无 BLOCKER 级问题，表单无需修正"
          style={{ margin: '24px 0' }}
        />
      ) : cards.length > 0 ? (
        <Collapse
          defaultActiveKey={cards.map((c) => String(c.issue_index))}
          items={cards.map((card) => ({
            key: String(card.issue_index),
            label: (
              <span>
                <Tag color="red">{result.issues[card.issue_index]?.code ?? 'ISSUE'}</Tag>
                <Typography.Text strong style={{ fontSize: 12 }}>
                  {card.title}
                </Typography.Text>
                {card.field && (
                  <Typography.Text code style={{ fontSize: 11, marginLeft: 8 }}>
                    {card.field}
                  </Typography.Text>
                )}
              </span>
            ),
            children: (
              <>
                <Typography.Paragraph style={{ fontSize: 12, marginBottom: 8 }}>
                  <strong>原因：</strong>
                  {card.reason}
                </Typography.Paragraph>
                <Alert
                  type="info"
                  showIcon
                  message={
                    <span style={{ fontSize: 12 }}>
                      <strong>💡 修改建议：</strong>
                      {card.action}
                    </span>
                  }
                />
                <div style={{ marginTop: 8 }}>
                  <Tag style={{ fontSize: 10 }} color={card.action_source === 'AGENT' ? 'purple' : 'blue'}>
                    {card.action_source === 'AGENT' ? 'AGENT 建议' : 'RULE 建议'}
                  </Tag>
                  <Tag style={{ fontSize: 10 }}>
                    置信度 {(card.confidence * 100).toFixed(0)}%
                  </Tag>
                </div>
              </>
            ),
          }))}
        />
      ) : (
        <Collapse
          defaultActiveKey={blockers.map((b) => String(b.index))}
          items={blockers.map(({ issue, index }) => ({
            key: String(index),
            label: (
              <span>
                <Tag color="red">{issue.code}</Tag>
                {issue.field && (
                  <Typography.Text code style={{ fontSize: 11 }}>
                    field: {issue.field}
                  </Typography.Text>
                )}
              </span>
            ),
            children: (
              <Typography.Paragraph style={{ fontSize: 12, marginBottom: 0 }}>
                {issue.message}
              </Typography.Paragraph>
            ),
          }))}
        />
      )}
    </Card>
  );
};

export default RemediationCards;
