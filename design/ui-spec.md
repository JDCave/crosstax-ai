# CrossTax AI — React UI 设计规范

> **版本：** v1.0 | **日期：** 2026-10-22 | **作者：** PM + Designer
> **输入来源：** `specs/prd.md` §F8
> **状态：** 草案，待团队评审
> **技术栈：** React 18 + TypeScript + Vite + Ant Design 5.x

---

## 1. 设计概述

### 1.1 设计目标

为 CrossTax AI 合规审核引擎设计一套 React 单页应用（SPA），满足以下目标：

- **竞赛演示**：5 个典型 Case 一键切换，三态裁决完整展示
- **操作直觉**：上传即审核，结果一目了然
- **信息密度**：数据驱动，高 data-ink ratio，避免装饰
- **技术亮点**：规则热重载可视化、审计底稿可溯源、WebSocket 实时流水线状态

### 1.2 用户角色与界面映射

| 角色 | 界面区域 | 核心操作 |
|------|----------|----------|
| 商户 | 文件上传、修复卡片 | 上传 CRS 表单、查看整改建议 |
| 合规官 | 裁决横幅、冲突证据链、审计底稿 | 审核冲突、下载报告 |
| 管理员 | 规则版本、热重载按钮 | 加载规则补丁、验证生效 |
| 评审 | 全部区域 | 切换 Case、观察完整流程 |

### 1.3 技术选型

| 类别 | 选型 | 说明 |
|------|------|------|
| 框架 | React 18 | 函数式组件 + Hooks |
| 语言 | TypeScript | 严格类型约束 |
| 构建 | Vite | 快速 HMR，竞赛开发友好 |
| UI 库 | Ant Design 5.x | 企业级组件丰富，开箱即用 |
| 状态管理 | Zustand | 轻量、无模板代码 |
| 数据请求 | TanStack Query (React Query) | 缓存、重试、乐观更新 |
| 实时通信 | 原生 WebSocket（封装为 Hook） | 流水线状态推送 |
| 路由 | React Router v6 | 单页内多视图切换 |
| 样式 | CSS Modules + Ant Design Token | 组件隔离 + 设计令牌 |

---

## 2. 布局规范

### 2.1 整体结构

```
┌─────────────────────────────────────────────────┐
│  Header (64px)                                   │
│  Logo + 应用名 + 全局状态（规则版本）            │
├──────────┬──────────────────────────────────────┤
│ Sider    │  Content                             │
│ (260px)  │  (flex: 1)                           │
│          │                                      │
│ • 样本选择│  • PipelineStatus (Steps)            │
│ • 文件上传│  • VerdictBanner (Alert)             │
│ • 规则版本│  • DataGrid (2-col)                  │
│ • 热重载  │  • AuditTrail (Collapse)             │
│          │                                      │
└──────────┴──────────────────────────────────────┘
```

### 2.2 响应式断点

| 断点 | 宽度 | 布局调整 |
|------|------|----------|
| Desktop | ≥ 1280px | 标准双栏（Sider + Content） |
| Small Desktop | 992–1279px | Sider 可折叠 |
| Tablet | 768–991px | Sider 抽屉式 |
| Mobile | < 768px | 不支撑（竞赛演示场景） |

### 2.3 尺寸与间距

| 属性 | 值 | 说明 |
|------|-----|------|
| Header 高度 | 64px | Ant Design Layout.Header 默认 |
| Sider 宽度 | 260px | 展开态 |
| Sider 折叠宽度 | 80px | 仅图标 |
| Content 内边距 | 24px | Ant Design 默认 |
| 组件间距 | 16px | 同区块内 |
| 区块间距 | 24px | 不同区块间 |
| Grid 列数 | 2 (1:1) | Ant Design Row + Col span=12 |

---

## 3. 页面状态设计

### 3.1 五种核心状态

| 状态 | 对应 Case | 裁决 | 关键展示 |
|------|-----------|------|----------|
| **初始态** | — | — | 空上传区 + 引导文案 |
| **审核中** | 任意 | — | Pipeline 逐步点亮 + WebSocket 实时状态 |
| **AUTO_PASS** | Case A | 绿色横幅 | 全字段通过 + 校验结果 |
| **NEED_USER_FIX** | Case B/C | 红色横幅 | 修复卡片（字段级提示） |
| **MANUAL_TRIAGE** | Case D | 琥珀色横幅 | 冲突证据链 + 置信度 |

### 3.2 状态流转

```
初始态 → [上传文件] → 审核中 → [WebSocket 推送] → AUTO_PASS / NEED_USER_FIX / MANUAL_TRIAGE
                                                              │
                                                              └→ [切换 Case] → 审核中 → ...
```

### 3.3 WebSocket 实时状态

```typescript
// hooks/useAuditStream.ts
const useAuditStream = (sessionId: string | null) => {
  const [steps, setSteps] = useState<PipelineStep[]>([]);

  useEffect(() => {
    if (!sessionId) return;
    const ws = new WebSocket(`${WS_BASE}/ws/audit/${sessionId}`);
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setSteps(prev => [...prev, data]);
    };
    return () => ws.close();
  }, [sessionId]);

  return steps;
};
```

---

## 4. 组件规范

### 4.1 裁决横幅 (VerdictBanner)

使用 Ant Design `Alert` 组件，按裁决类型切换语义：

```tsx
import { Alert } from 'antd';

const VerdictBanner: React.FC<{ verdict: Verdict }> = ({ verdict }) => {
  const config = {
    AUTO_PASS: {
      type: 'success',
      message: '✅ 审核通过 — 纳税声明自动生效',
    },
    NEED_USER_FIX: {
      type: 'error',
      message: `❌ 表单存在阻断级错误，需修正后重新提交 (${blockerCount} BLOCKERS)`,
    },
    MANUAL_TRIAGE: {
      type: 'warning',
      message: `⚠️ 检测到税籍指示冲突，需合规官人工复核 (${warningCount} WARNINGS)`,
    },
  }[verdict];

  return <Alert banner showIcon message={config.message} type={config.type} />;
};
```

### 4.2 流水线状态 (PipelineStatus)

使用 Ant Design `Steps` 组件，结合 WebSocket 实时更新：

```tsx
import { Steps } from 'antd';

const PipelineStatus: React.FC<{ steps: PipelineStep[] }> = ({ steps }) => (
  <Steps
    direction="vertical"
    current={steps.filter(s => s.status === 'complete').length}
    items={steps.map(step => ({
      title: step.label,
      description: step.message,
      status: step.status, // wait | process | finish | error
    }))}
  />
);
```

### 4.3 修复卡片 (RemediationCard)

使用 Ant Design `Collapse` 展示字段级问题：

```tsx
import { Collapse, Tag, Alert } from 'antd';

const RemediationCard: React.FC<{ issues: AuditIssue[] }> = ({ issues }) => (
  <Collapse
    items={issues
      .filter(i => i.severity === 'BLOCKER')
      .map(issue => ({
        key: issue.code,
        label: (
          <span>
            <Tag color="red">{issue.code}</Tag>
            字段: <code>{issue.field}</code>
          </span>
        ),
        children: (
          <>
            <p><strong>问题：</strong>{issue.message}</p>
            <Alert
              type="info"
              message="💡 修改建议"
              description={getRemediation(issue.code)}
              showIcon
            />
          </>
        ),
      }))}
  />
);
```

### 4.4 冲突证据链 (ConflictEvidence)

使用 Ant Design `Descriptions` + `Progress` 展示置信度：

```tsx
import { Descriptions, Progress, Collapse } from 'antd';

const ConflictEvidence: React.FC<{ conflicts: IndiciaIssue[] }> = ({ conflicts }) => (
  <Collapse
    items={conflicts.map(c => ({
      key: c.scenario,
      label: (
        <span>
          <Tag color="gold">{c.scenario}</Tag>
          置信度: <Progress percent={Math.round(c.confidence * 100)} size="small" />
        </span>
      ),
      children: (
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="申报值">{c.declaredValue}</Descriptions.Item>
          <Descriptions.Item label="底表值">{c.sourceValue}</Descriptions.Item>
          <Descriptions.Item label="冲突说明" span={2}>{c.description}</Descriptions.Item>
        </Descriptions>
      ),
    }))}
  />
);
```

### 4.5 数据表格 (CRSFormData)

使用 Ant Design `Table`：

```tsx
import { Table, Tag } from 'antd';

const DataTable: React.FC<{ data: CRSFormData }> = ({ data }) => {
  const columns = [
    { title: '字段', dataIndex: 'field', key: 'field' },
    { title: '值', dataIndex: 'value', key: 'value' },
    {
      title: '置信度',
      dataIndex: 'confidence',
      key: 'confidence',
      render: (v: number) => (
        <Tag color={v < 0.7 ? 'orange' : 'green'}>{(v * 100).toFixed(0)}%</Tag>
      ),
    },
  ];

  return <Table columns={columns} dataSource={toRows(data)} pagination={false} />;
};
```

### 4.6 审计底稿 (AuditTrail)

使用 Ant Design `Descriptions` + `Typography.Paragraph copyable`：

```tsx
import { Descriptions, Typography, Button } from 'antd';

const AuditTrail: React.FC<{ session: AuditSession }> = ({ session }) => (
  <div>
    <Descriptions
      bordered
      column={2}
      size="small"
      title="📋 审计底稿 · Audit Trail"
    >
      <Descriptions.Item label="Session ID">
        <Typography.Text copyable code>{session.sessionId}</Typography.Text>
      </Descriptions.Item>
      <Descriptions.Item label="Merchant ID">{session.merchantId}</Descriptions.Item>
      <Descriptions.Item label="File Hash">
        <Typography.Text copyable code>{session.fileHash}</Typography.Text>
      </Descriptions.Item>
      <Descriptions.Item label="Rule Version">{session.ruleVersionId}</Descriptions.Item>
      <Descriptions.Item label="Verdict">
        <Tag color={verdictColor(session.verdict)}>{session.verdict}</Tag>
      </Descriptions.Item>
      <Descriptions.Item label="Timestamp">{session.timestamp}</Descriptions.Item>
    </Descriptions>

    <Button
      type="primary"
      icon={<DownloadOutlined />}
      onClick={() => downloadReport(session.sessionId)}
    >
      下载 HTML 审计报告
    </Button>
  </div>
);
```

### 4.7 规则热重载 (RuleReload)

```tsx
import { Button, Card, Space, Typography, Spin, message } from 'antd';

const RuleReload: React.FC = () => {
  const { data: current } = useQuery(['rules'], fetchRules);
  const reloadMutation = useMutation(reloadRules, {
    onSuccess: (data) => message.success(`✓ 已加载 → ${data.version}`),
  });

  return (
    <Card title="规则版本管理" size="small">
      <Space direction="vertical" style={{ width: '100%' }}>
        <Typography.Text type="secondary">当前版本</Typography.Text>
        <Typography.Paragraph code>{current?.version}</Typography.Paragraph>

        <Button
          type="primary"
          icon={<SyncOutlined />}
          loading={reloadMutation.isLoading}
          onClick={() => reloadMutation.mutate()}
        >
          ⟳ 加载 OECD 规则补丁
        </Button>
      </Space>
    </Card>
  );
};
```

---

## 5. 色彩规范

### 5.1 语义色彩（基于 Ant Design Token）

| 语义 | Ant Design Token | 用途 |
|------|------------------|------|
| PASS / 成功 | `colorSuccess` (#52c41a) | AUTO_PASS、校验通过 |
| FIX / 错误 | `colorError` (#ff4d4f) | NEED_USER_FIX、BLOCKER |
| TRIAGE / 警告 | `colorWarning` (#faad14) | MANUAL_TRIAGE、WARNING |
| INFO / 信息 | `colorInfo` (#1677ff) | 链接、下载按钮 |

### 5.2 中性色

| 元素 | Ant Design Token | 说明 |
|------|------------------|------|
| 背景 | `colorBgLayout` (#f5f5f5) | 整体背景 |
| 画布 | `colorBgContainer` (#ffffff) | 卡片、面板 |
| 边框 | `colorBorder` (#d9d9d9) | 分割线 |
| 主文字 | `colorText` (rgba(0,0,0,0.88)) | 标题、正文 |
| 副文字 | `colorTextSecondary` (rgba(0,0,0,0.65)) | 标签、说明 |

---

## 6. 字体规范

| 类型 | 字体栈 | 用途 |
|------|--------|------|
| UI 字体 | `-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif` | 标题、正文、按钮（Ant Design 默认） |
| 数据字体 | `'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace` | 字段名、值、代码、版本号 |

### 字号层级（Ant Design 标准）

| 层级 | 字号 | 字重 | 用途 |
|------|------|------|------|
| H1 | 20px | 600 | 页面标题 |
| H2 | 16px | 600 | 区块标题 |
| Body | 14px | 400 | 正文内容 |
| Small | 12px | 400 | 标签、说明 |
| Code | 13px | 400 | 数据值、版本号 |

---

## 7. 交互规范

### 7.1 状态反馈

| 操作 | 反馈方式 | 时长 |
|------|----------|------|
| 文件上传 | `Spin` + `Progress` | 直到完成 |
| Pipeline 执行 | WebSocket 推送 → `Steps` 逐步点亮 | 每步 1–3s |
| 热重载 | `Button loading` → `message.success` | ≤ 3s |
| 报告下载 | `Button` 触发浏览器下载 | 即时 |
| 错误 | `message.error` 全局提示 | 3s 自动消失 |

### 7.2 错误处理

| 场景 | 处理方式 |
|------|----------|
| 文件格式不支持 | `message.error('仅支持 PDF / JPG / PNG / WEBP')` |
| Vision API 超时 | `Modal.warning` 提示切换手动输入模式 |
| 规则加载失败 | `message.error('规则文件解析失败，保持当前版本')` |
| 文件过大 (>50MB) | `message.warning('文件过大，请压缩后重试')` |
| WebSocket 断连 | 自动重连 + `Alert` 提示网络状态 |

### 7.3 可访问性

- 所有颜色对比度 ≥ 4.5:1（WCAG AA）
- 图标配合文字说明，不单独依赖颜色传达信息
- 键盘可导航（Ant Design 原生支持）
- ARIA 属性完备

---

## 8. 实现清单

### 8.1 文件结构

```
frontend/src/
├── main.tsx                       # React 入口
├── App.tsx                        # 根组件 + 路由
├── api/
│   ├── client.ts                  # Axios 实例 + 拦截器
│   ├── audit.ts                   # /api/v1/audit
│   ├── rules.ts                   # /api/v1/rules
│   └── cases.ts                   # /api/v1/cases
├── components/
│   ├── Layout/
│   │   ├── AppHeader.tsx          # 顶部导航
│   │   └── AppSider.tsx           # 侧边栏
│   ├── PipelineStatus/
│   │   └── PipelineSteps.tsx      # 流水线步骤
│   ├── VerdictBanner/
│   │   └── index.tsx              # 裁决横幅
│   ├── RemediationCard/
│   │   └── index.tsx              # 修复卡片
│   ├── ConflictEvidence/
│   │   └── index.tsx              # 冲突证据链
│   ├── DataTable/
│   │   └── CrsDataTable.tsx       # 抽取数据表格
│   ├── AuditTrail/
│   │   └── index.tsx              # 审计底稿
│   └── RuleReload/
│       └── index.tsx              # 规则热重载
├── pages/
│   ├── AuditPage.tsx              # 主审核页
│   └── CasesPage.tsx              # 样本切换页
├── hooks/
│   ├── useAuditStream.ts          # WebSocket 流水线状态
│   ├── useAuditSession.ts         # 审核会话查询
│   └── useRules.ts                # 规则管理
├── stores/
│   └── auditStore.ts              # Zustand 全局状态
├── types/
│   ├── audit.ts                   # 审核相关类型
│   ├── rules.ts                   # 规则相关类型
│   └── api.ts                     # API 通用类型
└── styles/
    ├── tokens.ts                  # Ant Design 主题令牌
    └── global.css                 # 全局样式
```

### 8.2 开发优先级

| 优先级 | 任务 | 估时 |
|--------|------|------|
| P0 | Vite + React + TS 工程初始化 | 0.5d |
| P0 | Ant Design 集成 + 主题令牌配置 | 0.5d |
| P0 | Layout（Header + Sider + Content） | 0.5d |
| P0 | Axios 客户端 + API 封装 | 0.5d |
| P0 | PipelineStatus + WebSocket Hook | 1d |
| P0 | VerdictBanner | 0.5d |
| P1 | 文件上传（react-dropzone） | 0.5d |
| P1 | DataTable | 0.5d |
| P1 | RemediationCard | 0.5d |
| P1 | ConflictEvidence | 0.5d |
| P1 | AuditTrail + 报告下载 | 0.5d |
| P1 | RuleReload | 0.5d |
| P2 | CasesPage 样本切换 | 0.5d |
| **合计** | | **6.5d** |

### 8.3 验收标准

- [ ] 5 个 Case 可一键切换，主区域自动刷新
- [ ] 三态裁决横幅颜色正确（绿/红/琥珀）
- [ ] BLOCKER 修复卡片字段级提示准确
- [ ] WARNING 冲突证据链高亮显示
- [ ] WebSocket 流水线状态实时推送，无延迟感
- [ ] 热重载按钮点击后 ≤ 3s 显示新版本
- [ ] 审计报告 HTML 可下载，含完整溯源信息
- [ ] 1280×720 分辨率下布局无错位
- [ ] TypeScript 严格模式无类型错误
- [ ] 单元测试覆盖核心组件与 Hooks

---

## 9. 参考文档

- [PRD §F8](../specs/prd.md) — React 演示 SPA + FastAPI 后端功能定义
- [架构设计](./architecture.md) — 展现层 + API 层设计
- [OpenAPI 契约](./openapi.yaml) — 前后端接口规范
- [Ant Design 文档](https://ant.design/) — 组件 API 参考
- [React 文档](https://react.dev/) — 框架参考
