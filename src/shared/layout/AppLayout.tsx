import { Layout, Menu, Typography } from 'antd';
import { Link, Outlet, useLocation } from 'react-router-dom';

const menuItems = [
  { key: '/models', label: <Link to="/models">Models</Link> },
  { key: '/data', label: <Link to="/data">Data</Link> },
  { key: '/events', label: <Link to="/events">Events</Link> },
  { key: '/settings', label: <Link to="/settings">Prefs</Link> },
];

function getSelectedMenuKey(pathname: string): string {
  if (pathname.startsWith('/settings')) return '/settings';
  if (pathname.startsWith('/events')) return '/events';
  if (pathname.startsWith('/data')) return '/data';
  return '/models';
}

export function AppLayout() {
  const location = useLocation();

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Layout.Sider width={88} theme="light" style={{ borderRight: '1px solid #d7e1ea' }}>
        <div style={{ padding: '12px 10px', textAlign: 'center' }}>
          <Typography.Text strong>Studio</Typography.Text>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[getSelectedMenuKey(location.pathname)]}
          items={menuItems}
          style={{ borderInlineEnd: 0 }}
        />
      </Layout.Sider>
      <Layout>
        <Layout.Content style={{ padding: 24 }}>
          <Outlet />
        </Layout.Content>
      </Layout>
    </Layout>
  );
}
