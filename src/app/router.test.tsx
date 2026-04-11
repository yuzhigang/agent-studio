import { render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { beforeEach } from 'vitest';
import { modelService } from '@/mocks/services/modelService';
import { appRoutes } from './router';

function renderWithRoute(pathname: string) {
  const router = createMemoryRouter(appRoutes, {
    initialEntries: [pathname],
  });

  render(<RouterProvider router={router} />);
}

beforeEach(async () => {
  localStorage.clear();
  await modelService.reset();
});

test('redirects / to /models and renders layout navigation', async () => {
  renderWithRoute('/');

  expect(await screen.findByRole('link', { name: 'Models' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Settings' })).toBeInTheDocument();
  expect(await screen.findByRole('heading', { name: 'Models' })).toBeInTheDocument();
});

test('renders /settings route', async () => {
  renderWithRoute('/settings');

  expect(await screen.findByRole('heading', { name: 'Settings' })).toBeInTheDocument();
});

test('renders /models/:modelId route', async () => {
  renderWithRoute('/models/ladle');

  expect(await screen.findByDisplayValue('钢包智能体')).toBeInTheDocument();
});

test('renders /models/:modelId/instances/:instanceId route', async () => {
  renderWithRoute('/models/ladle/instances/ladle_001');

  expect(await screen.findByRole('heading', { name: 'Instance Detail' })).toBeInTheDocument();
});
