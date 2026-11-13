import React from 'react';
import { Alert, Button, Col, Empty, Row, Space, Spin, Tag, Typography } from 'antd';
import { PlayCircleOutlined } from '@ant-design/icons';
import PipelineSteps from '../components/PipelineSteps';
import VerdictBanner from '../components/VerdictBanner';
import CrsDataTable from '../components/CrsDataTable';
import RemediationCards from '../components/RemediationCards';
import ConflictEvidence from '../components/ConflictEvidence';
import ValidationChecks from '../components/ValidationChecks';
import AuditTrail from '../components/AuditTrail';
import { useAuditStore } from '../stores/auditStore';
import { useAuditTask } from '../hooks/useAuditTask';

/**
 * 主审核页：Pipeline → Verdict → 双栏数据网格 → 校验明细 → 审计底稿
 */
const AuditPage: React.FC = () => {
  const activeCase = useAuditStore((s) => s.activeCase);
  const apiMode = useAuditStore((s) => s.apiMode);
  const currentTask = useAuditStore((s) => s.currentTask);
  const submittedFormData = useAuditStore((s) => s.submittedFormData);
  const submittedLabel = useAuditStore((s) => s.submittedLabel);
  const running = useAuditStore((s) => s.running);
  const sessionId = useAuditStore((s) => s.sessionId);
  const { run } = useAuditTask();

  const result = currentTask?.status === 'SUCCEEDED' ? currentTask.result : null;
  const failed = currentTask?.status === 'FAILED' ? currentTask : null;
  // 展示实际提交的表单数据与来源（上传/样例场景与当前 Case 可能不同）
  const displayFormData = submittedFormData ?? activeCase.form_data;
  const displayTitle = submittedLabel ?? activeCase.title;
  const displayDesc = submittedLabel ? 'doc 官方样例 / 自定义请求' : activeCase.description;

  return (
    <div style={{ maxWidth: 1400, margin: '0 auto' }}>
      {/* 内容标题 */}
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
            审核结果 — {displayTitle}
          </Typography.Title>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {displayDesc}
          </Typography.Text>
          {apiMode === 'sync' && <Tag color="blue">同步校验</Tag>}
        </Space>
        <Typography.Text type="secondary" style={{ fontSize: 11, fontFamily: 'monospace' }}>
          SESSION: {sessionId.slice(0, 8)}
        </Typography.Text>
      </div>

      {/* 流水线状态 */}
      <PipelineSteps />

      {/* 执行中 */}
      {running && (
        <div style={{ textAlign: 'center', padding: '48px 0' }}>
          <Spin size="large" />
          <div style={{ marginTop: 16, color: '#64748b' }}>
            规则引擎执行中，正在轮询任务状态…
          </div>
        </div>
      )}

      {/* 执行失败 */}
      {!running && failed && (
        <Alert
          banner
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          message="任务执行失败"
          description={`${failed.error?.code ?? 'UNKNOWN'} — ${failed.error?.message ?? '请确认 Worker 已启动并重试'}`}
        />
      )}

      {/* 空状态：尚未提交 */}
      {!running && !currentTask && (
        <div
          style={{
            textAlign: 'center',
            padding: '64px 24px',
            background: '#fff',
            border: '1px dashed #cbd5e1',
            borderRadius: 4,
          }}
        >
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <>
                <Typography.Text strong style={{ fontSize: 14 }}>
                  尚未提交审核
                </Typography.Text>
                <div style={{ color: '#64748b', marginTop: 8, fontSize: 12 }}>
                  选择左侧预置样本，或上传请求 JSON，点击「提交审核」开始五步流水线
                </div>
              </>
            }
          />
          <Button
            type="primary"
            size="large"
            icon={<PlayCircleOutlined />}
            style={{ marginTop: 16 }}
            onClick={() => void run()}
          >
            提交审核 · Case {activeCase.case_id}
          </Button>
        </div>
      )}

      {/* 审核结果 */}
      {!running && result && currentTask && (
        <>
          <VerdictBanner result={result} />

          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={12}>
              <CrsDataTable formData={displayFormData} issues={result.issues} />
            </Col>
            <Col span={12}>
              {result.issues.some((i) => i.severity === 'BLOCKER') ? (
                <RemediationCards result={result} />
              ) : (
                <ConflictEvidence result={result} />
              )}
            </Col>
          </Row>

          {result.issues.some((i) => i.severity === 'BLOCKER') &&
            result.issues.some((i) => i.severity === 'WARNING') && (
              <div style={{ marginBottom: 16 }}>
                <ConflictEvidence result={result} />
              </div>
            )}

          <div style={{ marginBottom: 16 }}>
            <ValidationChecks result={result} />
          </div>

          <AuditTrail task={currentTask} />
        </>
      )}
    </div>
  );
};

export default AuditPage;
