import React, { useCallback } from 'react';
import { App, Button, Card, Divider, Layout, Menu, Segmented, Space, Typography, Upload } from 'antd';
import {
  CloudUploadOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  ReloadOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import type { UploadProps } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useAuditStore } from '../../stores/auditStore';
import { DEMO_CASES } from '../../data/cases';
import { DOC_SAMPLES } from '../../data/sampleRequests';
import { useAuditTask } from '../../hooks/useAuditTask';
import type { ValidationRequest } from '../../types/api';

const { Sider } = Layout;

/**
 * 侧边栏：接口模式 / 样本选择 / doc 样例 / 请求 JSON 上传 / 规则版本 / 规则升级演示入口
 */
const AppSider: React.FC = () => {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const activeCase = useAuditStore((s) => s.activeCase);
  const selectCase = useAuditStore((s) => s.selectCase);
  const apiMode = useAuditStore((s) => s.apiMode);
  const setApiMode = useAuditStore((s) => s.setApiMode);
  const currentTask = useAuditStore((s) => s.currentTask);
  const running = useAuditStore((s) => s.running);
  const { run } = useAuditTask();

  /** 上传请求 JSON（对应 doc 中 crs-*-request.json 格式），解析后提交 */
  const beforeUpload = useCallback<NonNullable<UploadProps['beforeUpload']>>(
    async (file) => {
      try {
        const text = await file.text();
        const parsed = JSON.parse(text) as Partial<ValidationRequest> & {
          form_data?: unknown;
        };
        // 兼容 doc 样例的裸结构 { form_data, policy, indicia_issues }
        if (!parsed || typeof parsed !== 'object' || !parsed.form_data) {
          message.error('JSON 结构无效：需要包含 form_data 字段（参考 doc/crs-*-request.json）');
          return Upload.LIST_IGNORE;
        }
        const validation: ValidationRequest = {
          form_data: parsed.form_data as ValidationRequest['form_data'],
          policy: parsed.policy ?? { today: new Date().toISOString().slice(0, 10) },
          indicia_issues: parsed.indicia_issues ?? [],
        };
        message.success(`已加载请求文件：${file.name}，开始提交审核`);
        void run({ overrideValidation: validation, label: `上传文件 · ${file.name}` });
      } catch {
        message.error('文件解析失败：仅支持 UTF-8 编码的请求 JSON 文件');
      }
      return Upload.LIST_IGNORE;
    },
    [message, run],
  );

  return (
    <Sider
      width={260}
      theme="light"
      style={{
        borderRight: '1px solid #f0f0f0',
        padding: '16px 12px',
        overflow: 'auto',
        height: 'calc(100vh - 64px)',
        position: 'sticky',
        top: 64,
      }}
    >
      {/* 接口模式 */}
      <div style={{ marginBottom: 20 }}>
        <Typography.Text
          type="secondary"
          style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.5 }}
        >
          接口模式 · API Mode
        </Typography.Text>
        <Segmented
          block
          size="small"
          style={{ marginTop: 8 }}
          value={apiMode}
          disabled={running}
          onChange={(v) => setApiMode(v as 'async' | 'sync')}
          options={[
            { label: '异步任务', value: 'async' },
            { label: '同步校验', value: 'sync' },
          ]}
        />
        <Typography.Text type="secondary" style={{ fontSize: 10, display: 'block', marginTop: 4 }}>
          {apiMode === 'async'
            ? 'POST /tasks → 轮询（默认公开接口，支持 PDF 报告与补正对比）'
            : 'POST /validate 一次返回（doc 队友接入接口，无报告与对比）'}
        </Typography.Text>
      </div>

      <Divider style={{ margin: '12px 0' }} />

      {/* 样本选择 */}
      <div style={{ marginBottom: 20 }}>
        <Typography.Text
          type="secondary"
          style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.5 }}
        >
          样本选择 · Cases
        </Typography.Text>
        <Menu
          mode="inline"
          selectedKeys={[activeCase.case_id]}
          onClick={({ key }) => selectCase(key)}
          style={{ border: 'none', marginTop: 8 }}
          items={DEMO_CASES.map((c) => ({
            key: c.case_id,
            icon: <FileTextOutlined />,
            label: c.title,
            disabled: running,
          }))}
        />
      </div>

      {/* doc 官方样例 */}
      <div style={{ marginBottom: 20 }}>
        <Typography.Text
          type="secondary"
          style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.5 }}
        >
          doc 官方样例 · Samples
        </Typography.Text>
        <Space direction="vertical" style={{ width: '100%', marginTop: 8 }}>
          {DOC_SAMPLES.map((sample) => (
            <Button
              key={sample.key}
              block
              size="small"
              disabled={running}
              onClick={() => void run({ overrideValidation: sample.request, label: sample.title })}
            >
              {sample.title.replace('doc 样例 · ', '')}
            </Button>
          ))}
        </Space>
      </div>

      <Divider style={{ margin: '12px 0' }} />

      {/* 请求 JSON 上传 */}
      <div style={{ marginBottom: 20 }}>
        <Typography.Text
          type="secondary"
          style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.5 }}
        >
          请求上传 · Upload
        </Typography.Text>
        <Upload.Dragger
          accept=".json,application/json"
          multiple={false}
          showUploadList={false}
          beforeUpload={beforeUpload}
          disabled={running}
          style={{ marginTop: 8, padding: '4px 0' }}
        >
          <p style={{ margin: 4 }}>
            <CloudUploadOutlined style={{ fontSize: 26, color: '#2563eb' }} />
          </p>
          <p style={{ fontSize: 12, color: '#64748b', margin: 0 }}>
            拖拽 <strong>请求 JSON</strong> 至此
            <br />
            或点击选择文件
          </p>
        </Upload.Dragger>
        <Typography.Text type="secondary" style={{ fontSize: 11 }}>
          格式参考 doc/crs-templates 中 crs-*-request.json
        </Typography.Text>
      </div>

      <Divider style={{ margin: '12px 0' }} />

      {/* 规则版本 */}
      <div style={{ marginBottom: 20 }}>
        <Typography.Text
          type="secondary"
          style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.5 }}
        >
          规则版本 · Rules
        </Typography.Text>
        <Card size="small" style={{ marginTop: 8, fontFamily: 'monospace', fontSize: 11 }}>
          <div>
            <strong>VERSION:</strong> {currentTask?.rule_version_id ?? '—（提交审核后显示）'}
          </div>
          <div>
            <strong>REVISION:</strong>{' '}
            {currentTask?.rule_revision !== undefined ? `#${currentTask.rule_revision}` : '—'}
          </div>
          <div style={{ wordBreak: 'break-all' }}>
            <strong>BUILD:</strong>{' '}
            {currentTask?.engine_build_id ? `${currentTask.engine_build_id.slice(0, 12)}…` : '—'}
          </div>
        </Card>
      </div>

      {/* 规则升级演示入口 */}
      <Space direction="vertical" style={{ width: '100%' }}>
        <Button
          block
          icon={<ExperimentOutlined />}
          onClick={() => navigate('/demo/rule-upgrade')}
          disabled={running}
        >
          规则热重载演示
        </Button>
        <Button
          block
          type="primary"
          icon={running ? <SyncOutlined spin /> : <ReloadOutlined />}
          loading={running}
          onClick={() => void run()}
        >
          {running
            ? '审核中…'
            : apiMode === 'sync'
              ? `同步校验 · Case ${activeCase.case_id}`
              : `提交审核 · Case ${activeCase.case_id}`}
        </Button>
      </Space>
    </Sider>
  );
};

export default AppSider;
