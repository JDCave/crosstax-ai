import React from 'react';
import { Layout, Space, Tag, Typography } from 'antd';
import { SafetyCertificateOutlined } from '@ant-design/icons';
import { useAuditStore } from '../../stores/auditStore';

const { Header } = Layout;

/**
 * 顶部导航：Logo + 应用名 + 全局状态（规则版本 / 引擎构建 / 会话）
 */
const AppHeader: React.FC = () => {
  const currentTask = useAuditStore((s) => s.currentTask);
  const running = useAuditStore((s) => s.running);

  const ruleVersion = currentTask?.rule_version_id ?? '—';
  const ruleRevision = currentTask?.rule_revision;

  return (
    <Header
      style={{
        height: 64,
        padding: '0 24px',
        background: '#fff',
        borderBottom: '1px solid #f0f0f0',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        position: 'sticky',
        top: 0,
        zIndex: 10,
      }}
    >
      <Space size={12}>
        <div
          style={{
            width: 32,
            height: 32,
            border: '2px solid #0f172a',
            borderRadius: 4,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontWeight: 700,
            fontSize: 16,
          }}
        >
          C
        </div>
        <Typography.Title level={4} style={{ margin: 0, letterSpacing: -0.3 }}>
          CrossTax AI
        </Typography.Title>
        <Tag color="default" style={{ marginLeft: 4 }}>
          合规审核工作台
        </Tag>
      </Space>

      <Space size={16}>
        <Typography.Text type="secondary" style={{ fontFamily: 'monospace', fontSize: 12 }}>
          RULE VERSION:{' '}
          <Typography.Text strong style={{ fontFamily: 'monospace', fontSize: 12 }}>
            {ruleVersion}
            {ruleRevision !== undefined ? ` (rev ${ruleRevision})` : ''}
          </Typography.Text>
        </Typography.Text>
        <Tag
          icon={<SafetyCertificateOutlined />}
          color={running ? 'processing' : 'success'}
          style={{ fontFamily: 'monospace', fontSize: 11 }}
        >
          {running ? 'AUDIT RUNNING' : 'ENGINE LINKED'}
        </Tag>
      </Space>
    </Header>
  );
};

export default AppHeader;
