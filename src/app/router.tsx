import { Navigate, type RouteObject } from 'react-router-dom';
import { InstanceDetailPage } from '@/pages/instances/InstanceDetailPage';
import { ModelDetailPage } from '@/pages/models/ModelDetailPage';
import { ModelsPage } from '@/pages/models/ModelsPage';
import { SettingsPage } from '@/pages/settings/SettingsPage';
import { AppLayout } from '@/shared/layout/AppLayout';

export const appRoutes: RouteObject[] = [
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to="/models" replace /> },
      { path: 'models', element: <ModelsPage /> },
      { path: 'models/:modelId', element: <ModelDetailPage /> },
      { path: 'models/:modelId/instances/:instanceId', element: <InstanceDetailPage /> },
      { path: 'settings', element: <SettingsPage /> },
    ],
  },
];
