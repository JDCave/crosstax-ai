import React, { useState } from 'react';
import { App, Button, Card, Descriptions, Modal, Space, Table, Tag, Typography } from 'antd';
import {
  DiffOutlined,
  DownloadOutlined,
  FileProtectOutlined,
  LoadingOutlined,
} from '@ant-design/icons';
import { reportDownloadUrl, getTask } from '../api/tasks';
import { useAuditStore } from '../stores/auditStore';
import type { TaskComparison, TaskResponse } from '../types/api';

const VERDICT_COLOR: Record<string, string> = {
  AUTO_PASS: 'green',
  NEED_USER_FIX: 'red',
  MANUAL_TRIAGE: 'orange',
};

/**
 * 审计底稿（Descriptions）：
 * 会话/任务快照 + 规则版本绑定 + 输入指纹 + PDF 报告下载 + 补正前后对比
 */
const AuditTrail: React.FC<{ task: TaskResponse }> = ({ task }) => {
  const { message } = App.useApp();
  const succeededHistory = useAuditStore((s) => s.succeededHistory);
  const [comparison, setComparison] = useState<TaskComparison | null>(null);
  const [compareOpen, setCompareOpen] = useState(false);
  const [comparing, setComparing] = useState(false);

  // 同会话内、当前任务之前的成功异步任务可作为补正前基线（同步校验无真实 task_id，排除）
  const isSyncTask = task.task_id === 'sync';
  const baseline = [...succeededHistory]
    .reverse()
    .find(
      (r) =>
        r.task.task_id !== task.task_id &&
        r.task.task_id !== 'sync' &&
        r.task.session_id === task.session_id,
    );

  const result = task.result;

  const handleCompare = async () => {
    if (!baseline) return;
    setComparing(true);
    try {
      const compared = await getTask(task.task_id, baseline.task.task_id);
      if (compared.comparison) {
        setComparison(compared.comparison);
        setCompareOpen(true);
      } else {
        message.warning('对比不可用：两任务需同会话且均成功');
      }
    } catch {
      message.error('对比请求失败，请稍后重试');
    } finally {
      setComparing(false);
    }
  };

  return (
    <Card
      size="small"
      title={
        <span>
          <FileProtectOutlined /> 审计底稿 · Audit Trail
        </span>
      }
      extra={
        <Space>
          {baseline && !isSyncTask && (
            <Button
              size="small"
              icon={comparing ? <LoadingOutlined /> : <DiffOutlined />}
              onClick={() => void handleCompare()}
              disabled={comparing}
            >
              补正对比
            </Button>
          )}
          {isSyncTask ? (
            <Button size="small" icon={<DownloadOutlined />} disabled>
              同步模式无报告
            </Button>
          ) : task.report_status === 'READY' ? (
            <Button
              size="small"
              type="primary"
              icon={<DownloadOutlined />}
              href={reportDownloadUrl(task.task_id)}
              download
            >
              下载 PDF 报告
            </Button>
          ) : (
            <Button size="small" icon={<DownloadOutlined />} disabled>
              {task.report_status === 'FAILED'
                ? '报告生成失败'
                : task.report_status === 'PENDING' || task.report_status === 'RUNNING'
                  ? '报告生成中…'
                  : '报告不可用'}
            </Button>
          )}
        </Space>
      }
    >
      <Descriptions size="small" column={2} bordered>
        <Descriptions.Item label="session_id">
          <Typography.Text copyable code style={{ fontSize: 11 }}>
            {task.session_id}
          </Typography.Text>
        </Descriptions.Item>
        <Descriptions.Item label="task_id">
          {isSyncTask ? (
            <Tag color="blue" style={{ fontSize: 10 }}>
              同步校验（无任务）
            </Tag>
          ) : (
            <Typography.Text copyable code style={{ fontSize: 11 }}>
              {task.task_id}
            </Typography.Text>
          )}
        </Descriptions.Item>
        <Descriptions.Item label="rule_version_id">
          <Typography.Text code style={{ fontSize: 11 }}>
            {task.rule_version_id}
          </Typography.Text>
        </Descriptions.Item>
        <Descriptions.Item label="rule_revision">#{task.rule_revision}</Descriptions.Item>
        <Descriptions.Item label="engine_build_id">
          <Typography.Text copyable code style={{ fontSize: 11 }}>
            {task.engine_build_id.slice(0, 16)}…
          </Typography.Text>
        </Descriptions.Item>
        <Descriptions.Item label="input_fingerprint">
          <Typography.Text copyable code style={{ fontSize: 11 }}>
            {result?.execution?.input_fingerprint
              ? `${result.execution.input_fingerprint.slice(0, 16)}…`
              : '—'}
          </Typography.Text>
        </Descriptions.Item>
        <Descriptions.Item label="verdict">
          {result ? (
            <Tag color={VERDICT_COLOR[result.verdict]} style={{ fontFamily: 'monospace' }}>
              {result.verdict}
            </Tag>
          ) : (
            '—'
          )}
        </Descriptions.Item>
        <Descriptions.Item label="report_status">
          {task.report_status ? (
            <Tag color={task.report_status === 'READY' ? 'green' : task.report_status === 'FAILED' ? 'red' : 'processing'}>
              {task.report_status}
            </Tag>
          ) : (
            '—'
          )}
        </Descriptions.Item>
        <Descriptions.Item label="created_at">
          <Typography.Text style={{ fontSize: 11, fontFamily: 'monospace' }}>
            {new Date(task.created_at).toLocaleString('zh-CN')}
          </Typography.Text>
        </Descriptions.Item>
        <Descriptions.Item label="completed_at">
          <Typography.Text style={{ fontSize: 11, fontFamily: 'monospace' }}>
            {task.completed_at ? new Date(task.completed_at).toLocaleString('zh-CN') : '—'}
          </Typography.Text>
        </Descriptions.Item>
      </Descriptions>

      <Modal
        open={compareOpen}
        title="补正前后对比 · Task Comparison"
        width={720}
        footer={null}
        onCancel={() => setCompareOpen(false)}
      >
        {comparison && (
          <>
            <Descriptions size="small" column={2} bordered style={{ marginBottom: 12 }}>
              <Descriptions.Item label="修复前 verdict">
                <Tag color={VERDICT_COLOR[comparison.before_verdict] ?? 'default'}>
                  {comparison.before_verdict}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="修复后 verdict">
                <Tag color={VERDICT_COLOR[comparison.after_verdict] ?? 'default'}>
                  {comparison.after_verdict}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="执行上下文">
                <Tag color={comparison.context === 'SAME_CONTEXT' ? 'green' : 'orange'}>
                  {comparison.context}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="变更字段数">{comparison.changed_field_count}</Descriptions.Item>
            </Descriptions>

            {comparison.context === 'DIFFERENT_CONTEXT' && (
              <Typography.Paragraph type="warning" style={{ fontSize: 12 }}>
                ⚠ 两次执行的规则/日期/构建上下文不同（{comparison.context_changes.join('、')}），
                结论差异不能完全归因于用户补正。
              </Typography.Paragraph>
            )}

            <Typography.Paragraph style={{ fontSize: 12 }}>
              {comparison.statement}
            </Typography.Paragraph>

            <Table
              size="small"
              pagination={false}
              rowKey={(r) => `${r.code}-${r.field}-${r.origin}`}
              dataSource={[
                ...comparison.resolved.map((r) => ({ ...r, _kind: '已解决' })),
                ...comparison.introduced.map((r) => ({ ...r, _kind: '新引入' })),
                ...comparison.remaining.map((r) => ({ ...r, _kind: '仍存在' })),
              ]}
              columns={[
                {
                  title: '变化',
                  dataIndex: '_kind',
                  width: 90,
                  render: (kind: string) => (
                    <Tag color={kind === '已解决' ? 'green' : kind === '新引入' ? 'red' : 'orange'}>
                      {kind}
                    </Tag>
                  ),
                },
                { title: 'code', dataIndex: 'code', render: (c: string) => <Typography.Text code style={{ fontSize: 11 }}>{c}</Typography.Text> },
                { title: 'field', dataIndex: 'field', render: (f: string | null) => f ?? '—' },
                { title: 'severity', dataIndex: 'severity', width: 100 },
                { title: '次数', dataIndex: 'count', width: 60 },
              ]}
            />
            {comparison.changed_fields.length > 0 && (
              <div style={{ marginTop: 12 }}>
                <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                  变更字段路径（不返回原值）：{comparison.changed_fields.join('、')}
                  {comparison.changed_fields_truncated ? ' …（已截断）' : ''}
                </Typography.Text>
              </div>
            )}
          </>
        )}
      </Modal>
    </Card>
  );
};

export default AuditTrail;
