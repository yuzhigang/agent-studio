import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { beforeEach, test } from 'vitest';
import { instanceService } from '@/mocks/services/instanceService';
import { modelService } from '@/mocks/services/modelService';
import { ModelsPage } from './ModelsPage';

function renderModelsPage(pathname = '/models') {
  const router = createMemoryRouter(
    [
      { path: '/models', element: <ModelsPage /> },
      { path: '/models/:modelId', element: <ModelsPage /> },
      { path: '/models/:modelId/instances/:instanceId', element: <ModelsPage /> },
    ],
    { initialEntries: [pathname] },
  );
  render(<RouterProvider router={router} />);
  return router;
}

beforeEach(async () => {
  localStorage.clear();
  await Promise.all([modelService.reset(), instanceService.reset()]);
});

test('renders the workbench page with embedded detail pane', async () => {
  renderModelsPage('/models/ladle/instances/ladle_001');

  await screen.findByRole('heading', { name: 'Instances' });
  await screen.findByDisplayValue('1号钢包');
  expect(screen.getByRole('button', { name: /ladle_001/i })).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument();
});

test('creates a new model in the workbench', async () => {
  const user = userEvent.setup();

  renderModelsPage('/models');

  await screen.findByRole('button', { name: '钢包智能体' });

  await user.click(screen.getByRole('button', { name: 'New Model' }));
  await user.type(screen.getByLabelText('Name'), 'scheduler');
  await user.type(screen.getByLabelText('Title'), '调度智能体');
  await user.click(screen.getByRole('button', { name: 'Create' }));

  expect(await screen.findByRole('button', { name: '调度智能体' })).toBeInTheDocument();
});

test('rejects duplicate model name on create', async () => {
  const user = userEvent.setup();

  renderModelsPage('/models');

  await screen.findByRole('button', { name: '钢包智能体' });

  await user.click(screen.getByRole('button', { name: 'New Model' }));
  await user.type(screen.getByLabelText('Name'), 'ladle');
  await user.type(screen.getByLabelText('Title'), '重复名智能体');
  await user.click(screen.getByRole('button', { name: 'Create' }));

  expect(await screen.findByText('Model name already exists')).toBeInTheDocument();
});

test('rejects route-hostile model name on create', async () => {
  const user = userEvent.setup();

  renderModelsPage('/models');

  await screen.findByRole('button', { name: '钢包智能体' });

  await user.click(screen.getByRole('button', { name: 'New Model' }));
  await user.type(screen.getByLabelText('Name'), 'bad/name');
  await user.type(screen.getByLabelText('Title'), '非法路由名');
  await user.click(screen.getByRole('button', { name: 'Create' }));

  expect(await screen.findByText('Name can only include letters, numbers, "_" and "-"')).toBeInTheDocument();
});
