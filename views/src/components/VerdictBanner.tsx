import React from 'react';
import { Alert, Tag } from 'antd';
import type { ValidationResponse } from '../types/api';

/**
 * 裁决横幅（Alert）：按 verdict 三态切换语义
 * AUTO_PASS 绿 / NEED_USER_FIX 红 / MANUAL_TRIAGE 琥珀
 */
const VerdictBanner: React.FC<{ result: ValidationResponse }> = ({ result }) => {
  const blockers = result.issues.filter((i) => i.severity === 'BLOCKER');
  const warnings = result.issues.filter((i) => i.severity === 'WARNING');

  const config = {
    AUTO_PASS: {
      type: 'success' as const,
      badge: 'green' as const,
      message: '审核通过 — 纳税声明自动生效',
      description: '所有已执行校验项通过，无阻断级错误，无待复核预警',
    },
    NEED_USER_FIX: {
      type: 'error' as const,
      badge: 'red' as const,
      message: '表单存在阻断级错误，需修正后重新提交',
      description: `检测到 ${blockers.length} 个 BLOCKER 级别问题，请根据修复建议修正后重新上传`,
    },
    MANUAL_TRIAGE: {
      type: 'warning' as const,
      badge: 'orange' as const,
      message: '检测到税籍指示冲突，需合规官人工复核',
      description: `发现 ${warnings.length} 个 WARNING 级别问题，请查看冲突证据链后决策`,
    },
  }[result.verdict];

  return (
    <Alert
      banner
      showIcon
      type={config.type}
      style={{ marginBottom: 16 }}
      message={
        <span>
          {config.message}
          <Tag color={config.badge} style={{ marginLeft: 12, fontFamily: 'monospace' }}>
            {result.verdict}
          </Tag>
        </span>
      }
      description={config.description}
    />
  );
};

export default VerdictBanner;
