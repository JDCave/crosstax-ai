import React from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Row,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
} from 'antd';
import { ArrowRightOutlined, ExperimentOutlined, ReloadOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getUpgradeImpact } from '../api/demo';
import { ApiError } from '../api/client';
import type { ImpactCaseRow } from '../types/api';

const VERDICT_COLOR: Record<string, string> = {
  AUTO_PASS: 'green',
  NEED_USER_FIX: 'red',
  MANUAL_TRIAGE: 'orange',
};

const RISK_LABELS: Record<string, string> = {
  SELECTOR_REMOVED: '规则被移除',
  VERIFICATION_DOWNGRADED: '校验深度降级',
  BLOCKER_REMOVED: 'BLOCKER 被解除',
  VERDICT_RELAXED: '裁决放宽',
  PASS_BECAME_BLOCKED: '通过变为阻断',
  SAMPLE_VERIFICATION_DOWNGRADED: '样本校验深度降级',
};

/**
 * 规则热重载演示页（Screen 4）：
 * 调用 GET /api/v1/rule-engine/demo/upgrade-impact（只读模拟），
 * 展示 before/after 版本对比、用例裁决迁移、规则差异与风险。
 * 按 COMPETITION_API.md 要求：必须保留 simulation 模拟标记。
 */
const UpgradeDemoPage: React.FC = () => {
  const navigate = useNavigate();
  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['rule-upgrade-impact'],
    queryFn: ({ signal }) => getUpgradeImpact(signal),
    retry: false,
    staleTime: 60_000,
  });

  const notEnabled = error instanceof ApiError && error.status === 404;

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 16,
        }}
      >
        <Space>
          <Typography.Title level={5} style={{ margin: 0 }}>
            <ExperimentOutlined /> 规则热重载演示
          </Typography.Title>
          <Tag color="purple">SIMULATION</Tag>
        </Space>
        <Space>
          <Button onClick={() => navigate('/')}>返回审核工作台</Button>
          <Button
            type="primary"
            icon={<ReloadOutlined />}
            loading={isFetching}
            onClick={() => void refetch()}
          >
            重新加载演示数据
          </Button>
        </Space>
      </div>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="只读模拟演示"
        description="本页面对应 GET /api/v1/rule-engine/demo/upgrade-impact：仅读取仓库模拟补丁并复用离线分析器，不激活数据库版本、不切换实际活动规则，合成用例不代表最新官方法规。"
      />

      {isLoading && (
        <div style={{ textAlign: 'center', padding: '64px 0' }}>
          <Spin size="large" />
          <div style={{ marginTop: 16, color: '#64748b' }}>正在分析模拟补丁影响…</div>
        </div>
      )}

      {notEnabled && (
        <Alert
          type="warning"
          showIcon
          message="演示接口未开启（404）"
          description={
            <span>
              请在后端 <Typography.Text code>.env</Typography.Text> 中设置{' '}
              <Typography.Text code>RULE_DEMO_ENABLED=true</Typography.Text>{' '}
              并重启 API 服务后重试。此开关仅启用只读演示，不影响真实规则。
            </span>
          }
        />
      )}

      {error && !notEnabled && (
        <Alert
          type="error"
          showIcon
          message="演示数据加载失败"
          description={error instanceof Error ? error.message : '未知错误'}
        />
      )}

      {data && (
        <>
          <Alert
            type="success"
            showIcon
            style={{ marginBottom: 16 }}
            message="模拟补丁分析完成"
            description={data.statement}
          />

          {/* Before / After 版本对比 */}
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={10}>
              <Card size="small" title="BASE · 当前活动规则">
                <Descriptions size="small" column={1}>
                  <Descriptions.Item label="version_id">
                    <Typography.Text code style={{ fontSize: 11 }}>
                      {data.impact.base_version_id}
                    </Typography.Text>
                  </Descriptions.Item>
                  <Descriptions.Item label="revision">
                    #{data.impact.base_revision}
                  </Descriptions.Item>
                  <Descriptions.Item label="样本数">{data.impact.sample_count}</Descriptions.Item>
                </Descriptions>
              </Card>
            </Col>
            <Col
              span={4}
              style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}
            >
              <ArrowRightOutlined style={{ fontSize: 24, color: '#94a3b8' }} />
            </Col>
            <Col span={10}>
              <Card
                size="small"
                title={
                  <span>
                    CANDIDATE · 模拟补丁 <Tag color="green">SIMULATED</Tag>
                  </span>
                }
                style={{ borderColor: '#16a34a' }}
              >
                <Descriptions size="small" column={1}>
                  <Descriptions.Item label="version_id">
                    <Typography.Text code style={{ fontSize: 11 }}>
                      {data.impact.candidate_version_id}
                    </Typography.Text>
                  </Descriptions.Item>
                  <Descriptions.Item label="变化用例">
                    {data.impact.changed_case_count} / {data.impact.sample_count}
                  </Descriptions.Item>
                  <Descriptions.Item label="规则差异">
                    {data.impact.rule_changes.length} 项
                  </Descriptions.Item>
                </Descriptions>
              </Card>
            </Col>
          </Row>

          {/* 用例裁决迁移 */}
          <Card size="small" title="用例裁决迁移 · Case Transitions" style={{ marginBottom: 16 }}>
            <Table<ImpactCaseRow>
              dataSource={data.impact.cases}
              pagination={false}
              size="small"
              rowKey="case_id"
              columns={[
                {
                  title: 'Case',
                  dataIndex: 'case_id',
                  width: 80,
                  render: (id: string) => <Typography.Text strong>Case {id}</Typography.Text>,
                },
                {
                  title: '修复前（BASE）',
                  key: 'before',
                  render: (_, row) => (
                    <Tag color={VERDICT_COLOR[row.before.verdict] ?? 'default'}>
                      {row.before.verdict}
                    </Tag>
                  ),
                },
                {
                  title: '',
                  key: 'arrow',
                  width: 40,
                  render: () => <ArrowRightOutlined style={{ color: '#94a3b8' }} />,
                },
                {
                  title: '修复后（CANDIDATE）',
                  key: 'after',
                  render: (_, row) => (
                    <Tag color={VERDICT_COLOR[row.after.verdict] ?? 'default'}>
                      {row.after.verdict}
                    </Tag>
                  ),
                },
                {
                  title: '变化',
                  dataIndex: 'changed',
                  width: 90,
                  render: (changed: boolean) =>
                    changed ? <Tag color="orange">CHANGED</Tag> : <Tag>无变化</Tag>,
                },
                {
                  title: '修复后 findings',
                  key: 'findings',
                  render: (_, row) =>
                    row.after.findings.length === 0 ? (
                      <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                        无
                      </Typography.Text>
                    ) : (
                      row.after.findings.map((f, i) => (
                        <Tag
                          key={i}
                          color={f.severity === 'BLOCKER' ? 'red' : 'orange'}
                          style={{ fontSize: 10, fontFamily: 'monospace' }}
                        >
                          {f.code}
                          {f.field ? `:${f.field}` : ''}
                        </Tag>
                      ))
                    ),
                },
              ]}
            />
            <div style={{ marginTop: 8 }}>
              {Object.entries(data.impact.transitions).map(([transition, count]) => (
                <Tag key={transition} style={{ fontFamily: 'monospace', fontSize: 11 }}>
                  {transition} ×{count}
                </Tag>
              ))}
            </div>
          </Card>

          {/* 规则差异 + 风险 */}
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={14}>
              <Card size="small" title="规则差异 · Rule Changes" style={{ height: '100%' }}>
                <Table
                  dataSource={data.impact.rule_changes}
                  pagination={false}
                  size="small"
                  rowKey={(r) => r.selector.join('|')}
                  columns={[
                    {
                      title: '选择器（jurisdiction/type/variant）',
                      dataIndex: 'selector',
                      render: (selector: [string, string, string]) => (
                        <Typography.Text code style={{ fontSize: 11 }}>
                          {selector.filter(Boolean).join(' / ') || '(default)'}
                        </Typography.Text>
                      ),
                    },
                    {
                      title: '变化',
                      dataIndex: 'change',
                      width: 100,
                      render: (change: string) => (
                        <Tag
                          color={
                            change === 'ADDED' ? 'green' : change === 'REMOVED' ? 'red' : 'orange'
                          }
                        >
                          {change}
                        </Tag>
                      ),
                    },
                    {
                      title: '影响执行',
                      dataIndex: 'execution_changed',
                      width: 90,
                      render: (v: boolean) => (v ? <Tag color="orange">是</Tag> : '否'),
                    },
                    {
                      title: '变更字段',
                      dataIndex: 'changed_fields',
                      render: (fields: string[]) =>
                        fields.length ? (
                          <Typography.Text style={{ fontSize: 11, fontFamily: 'monospace' }}>
                            {fields.join(', ')}
                          </Typography.Text>
                        ) : (
                          '—'
                        ),
                    },
                  ]}
                />
              </Card>
            </Col>
            <Col span={10}>
              <Card size="small" title="风险标记 · Risks" style={{ height: '100%' }}>
                {data.impact.risks.length === 0 ? (
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    未检出风险标记
                  </Typography.Text>
                ) : (
                  <Space direction="vertical" style={{ width: '100%' }}>
                    {data.impact.risks.map((risk) => (
                      <Alert
                        key={risk}
                        type="warning"
                        showIcon
                        message={
                          <span style={{ fontSize: 12 }}>
                            <Typography.Text code style={{ fontSize: 11 }}>
                              {risk}
                            </Typography.Text>{' '}
                            {RISK_LABELS[risk] ?? ''}
                          </span>
                        }
                      />
                    ))}
                  </Space>
                )}
                <Descriptions size="small" column={1} style={{ marginTop: 16 }}>
                  <Descriptions.Item label="suite_hash">
                    <Typography.Text code style={{ fontSize: 10 }}>
                      {data.impact.suite_hash.slice(0, 24)}…
                    </Typography.Text>
                  </Descriptions.Item>
                  <Descriptions.Item label="report_hash">
                    <Typography.Text code style={{ fontSize: 10 }}>
                      {data.impact.report_hash.slice(0, 24)}…
                    </Typography.Text>
                  </Descriptions.Item>
                  <Descriptions.Item label="engine_build">
                    <Typography.Text code style={{ fontSize: 10 }}>
                      {data.impact.engine_build_id.slice(0, 24)}…
                    </Typography.Text>
                  </Descriptions.Item>
                </Descriptions>
              </Card>
            </Col>
          </Row>
        </>
      )}
    </div>
  );
};

export default UpgradeDemoPage;
