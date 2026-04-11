import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { beforeEach, test } from 'vitest';
import { instanceService } from '@/mocks/services/instanceService';
import { modelService } from '@/mocks/services/modelService';
import { ModelsPage } from './ModelsPage';

function renderModelsWorkbench(pathname = '/models/ladle') {
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
  await modelService.reset();
  await instanceService.reset();
});

test('shows instances for the current model and creates a new instance', async () => {
  renderModelsWorkbench();

  expect(await screen.findByRole('button', { name: /ladle_001/i })).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'New Instance' }));
  const dialog = await screen.findByRole('dialog', { name: 'Create Instance' });
  fireEvent.change(within(dialog).getByLabelText('Instance ID'), { target: { value: 'ladle_002' } });
  fireEvent.change(within(dialog).getByLabelText('Title'), { target: { value: '2号钢包' } });
  fireEvent.click(within(dialog).getByRole('button', { name: 'Create' }));

  await waitFor(
    () => {
      expect(screen.getByRole('button', { name: /ladle_002/i })).toHaveAttribute('aria-pressed', 'true');
    },
    { timeout: 5000 },
  );
});

test('rejects duplicate instance id at service boundary even when page-level list is stale', async () => {
  renderModelsWorkbench();

  expect(await screen.findByRole('button', { name: /ladle_001/i })).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'New Instance' }));
  const dialog = await screen.findByRole('dialog', { name: 'Create Instance' });
  fireEvent.change(within(dialog).getByLabelText('Instance ID'), { target: { value: 'ladle_003' } });
  fireEvent.change(within(dialog).getByLabelText('Title'), { target: { value: '3号钢包' } });

  const seed = structuredClone((await instanceService.listByModel('ladle'))[0]);
  await instanceService.create({
    ...seed,
    id: 'ladle_003',
    metadata: {
      ...seed.metadata,
      name: 'ladle_003',
      title: 'Injected 3号钢包',
    },
  });

  fireEvent.click(within(dialog).getByRole('button', { name: 'Create' }));

  await waitFor(async () => {
    const instances = await instanceService.listByModel('ladle');
    expect(instances.filter((instance) => instance.id === 'ladle_003')).toHaveLength(1);
  });
});
