import React from 'react';
import { Card, Steps } from 'antd';
import { PIPELINE_STEPS, useAuditStore } from '../stores/auditStore';

/**
 * 流水线五步状态（Steps 组件）
 * 提交后轮询驱动进度：接收材料 → 多模态提取 → 税规推理校验 → 跨源冲突研判 → 决策与闭环
 */
const PipelineSteps: React.FC = () => {
  const progress = useAuditStore((s) => s.pipelineProgress);
  const running = useAuditStore((s) => s.running);
  const currentTask = useAuditStore((s) => s.currentTask);

  const failed = currentTask?.status === 'FAILED';

  return (
    <Card size="small" style={{ marginBottom: 16 }} styles={{ body: { padding: '16px 24px 8px' } }}>
      <Steps
        size="small"
        current={progress}
        status={failed ? 'error' : running ? 'process' : progress >= PIPELINE_STEPS.length ? 'finish' : 'wait'}
        items={PIPELINE_STEPS.map((step, idx) => ({
          title: step.title,
          description:
            idx + 1 === progress && running
              ? '执行中…'
              : idx < progress
                ? '完成'
                : undefined,
        }))}
      />
    </Card>
  );
};

export default PipelineSteps;
