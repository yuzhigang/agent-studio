import { Layout, Menu, Typography } from 'antd';
import { Link, Outlet, useLocation } from 'react-router-dom';

const menuItems = [
  { key: '/models', label: <Link to="/models">Models</Link> },
  { key: '/settings', label: <Link to="/settings">Settings</Link> },
];

function getSelectedMenuKey(pathname: string): string {
  return pathname.startsWith('/settings') ? '/settings' : '/models';
}

export function AppLayout() {
  const location = useLocation();

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Layout.Sider width={220} theme="light" style={{ borderRight: '1px solid #d7e1ea' }}>
        <div style={{ padding: 20 }}>
          <Typography.Title level={4} style={{ margin: 0 }}>
            Agent Studio
          </Typography.Title>
        </div>
        <Menu mode="inline" selectedKeys={[getSelectedMenuKey(location.pathname)]} items={menuItems} />
      </Layout.Sider>
      <Layout>
        <Layout.Content style={{ padding: 24 }}>
          <Outlet />
        </Layout.Content>
      </Layout>
    </Layout>
  );
}
