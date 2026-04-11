import { Navigate, type RouteObject } from 'react-router-dom';
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
      { path: 'models/:modelId', element: <ModelsPage /> },
      { path: 'models/:modelId/instances/:instanceId', element: <ModelsPage /> },
      { path: 'data', element: <Navigate to="/models" replace /> },
      { path: 'events', element: <Navigate to="/models" replace /> },
      { path: 'settings', element: <SettingsPage /> },
    ],
  },
];
