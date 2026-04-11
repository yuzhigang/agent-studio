import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { beforeEach, test } from 'vitest';
import { instanceService } from '@/mocks/services/instanceService';
import { modelService } from '@/mocks/services/modelService';
import { ModelDetailPage } from './ModelDetailPage';

function renderModelDetail(pathname = '/models/ladle') {
  const router = createMemoryRouter([{ path: '/models/:modelId', element: <ModelDetailPage /> }], {
    initialEntries: [pathname],
  });
  render(<RouterProvider router={router} />);
  return router;
}

beforeEach(async () => {
  localStorage.clear();
  await modelService.reset();
  await instanceService.reset();
});

test('shows instances for the current model and creates a new instance', async () => {
  renderModelDetail();

  expect(await screen.findByText('1号钢包')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'New Instance' }));
  const dialog = await screen.findByRole('dialog', { name: 'Create Instance' });
  fireEvent.change(within(dialog).getByLabelText('Instance ID'), { target: { value: 'ladle_002' } });
  fireEvent.change(within(dialog).getByLabelText('Title'), { target: { value: '2号钢包' } });
  fireEvent.click(within(dialog).getByRole('button', { name: 'Create' }));

  expect(await screen.findByText('2号钢包')).toBeInTheDocument();
});

test('rejects duplicate instance id at service boundary even when page-level list is stale', async () => {
  renderModelDetail();

  expect(await screen.findByText('1号钢包')).toBeInTheDocument();

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
