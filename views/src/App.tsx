import React from 'react';
import { App as AntApp, ConfigProvider, Layout } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { HashRouter, Navigate, Route, Routes } from 'react-router-dom';
import AppHeader from './components/layout/AppHeader';
import AppSider from './components/layout/AppSider';
import AuditPage from './pages/AuditPage';
import UpgradeDemoPage from './pages/UpgradeDemoPage';

const { Content } = Layout;

/**
 * 根组件：Ant Design 主题令牌 + 路由 + 整体布局
 * 色彩规范对齐 ui-spec.md §5（success/warning/error/info）
 */
const App: React.FC = () => {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorSuccess: '#16a34a',
          colorError: '#dc2626',
          colorWarning: '#d97706',
          colorInfo: '#2563eb',
          colorPrimary: '#2563eb',
          borderRadius: 2,
          fontFamily:
            "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'PingFang SC', 'Microsoft YaHei', sans-serif",
        },
        components: {
          Layout: {
            headerBg: '#ffffff',
            siderBg: '#ffffff',
            bodyBg: '#f8fafc',
          },
        },
      }}
    >
      <AntApp>
        <HashRouter>
          <Layout style={{ minHeight: '100vh' }}>
            <AppHeader />
            <Layout>
              <AppSider />
              <Content style={{ padding: 24, overflow: 'auto' }}>
                <Routes>
                  <Route path="/" element={<AuditPage />} />
                  <Route path="/demo/rule-upgrade" element={<UpgradeDemoPage />} />
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </Content>
            </Layout>
          </Layout>
        </HashRouter>
      </AntApp>
    </ConfigProvider>
  );
};

export default App;
