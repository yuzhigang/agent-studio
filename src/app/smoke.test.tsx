import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { beforeEach, test, vi } from 'vitest';
import { instanceService } from '@/mocks/services/instanceService';
import { modelService } from '@/mocks/services/modelService';
import { appRoutes } from './router';

beforeEach(async () => {
  localStorage.clear();
  await Promise.all([modelService.reset(), instanceService.reset()]);
});

test('navigates from models to settings', async () => {
  const router = createMemoryRouter(appRoutes, {
    initialEntries: ['/models'],
  });

  render(<RouterProvider router={router} />);

  expect(await screen.findByRole('heading', { name: 'Models' })).toBeInTheDocument();
  await router.navigate('/settings');
  expect(await screen.findByRole('heading', { name: 'Settings' })).toBeInTheDocument();
});

test('renders detail routes with seed-backed content', async () => {
  const modelRouter = createMemoryRouter(appRoutes, {
    initialEntries: ['/models/ladle'],
  });
  render(<RouterProvider router={modelRouter} />);
  expect(await screen.findByRole('button', { name: '钢包智能体' })).toHaveAttribute('aria-pressed', 'true');
  expect(await screen.findByRole('button', { name: /ladle_001/i })).toBeInTheDocument();

  const instanceRouter = createMemoryRouter(appRoutes, {
    initialEntries: ['/models/ladle/instances/ladle_001'],
  });
  render(<RouterProvider router={instanceRouter} />);
  expect(await screen.findByDisplayValue('1号钢包')).toBeInTheDocument();
});

test('blocks route navigation when there are unsaved changes and user cancels leave', async () => {
  const user = userEvent.setup();
  const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
  const router = createMemoryRouter(appRoutes, {
    initialEntries: ['/models/ladle/instances/ladle_001'],
  });

  render(<RouterProvider router={router} />);
  expect(await screen.findByDisplayValue('1号钢包')).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Unsaved title' } });
  await user.click(screen.getByRole('link', { name: 'Prefs' }));

  await waitFor(() => {
    expect(confirmSpy).toHaveBeenCalledWith('You have unsaved changes. Leave anyway?');
  });
  expect(router.state.location.pathname).toBe('/models/ladle/instances/ladle_001');
  expect(screen.queryByRole('heading', { name: 'Settings' })).not.toBeInTheDocument();

  confirmSpy.mockRestore();
});
