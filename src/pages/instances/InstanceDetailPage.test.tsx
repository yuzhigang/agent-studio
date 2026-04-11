import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { beforeEach, test } from 'vitest';
import { instanceService } from '@/mocks/services/instanceService';
import { modelService } from '@/mocks/services/modelService';
import { InstanceDetailPage } from './InstanceDetailPage';

function renderInstanceDetail(pathname = '/models/ladle/instances/ladle_001') {
  const router = createMemoryRouter([{ path: '/models/:modelId/instances/:instanceId', element: <InstanceDetailPage /> }], {
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

test('edits instance variables and bindings and saves them', async () => {
  renderInstanceDetail();

  expect(await screen.findByDisplayValue('1号钢包')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('tab', { name: 'Variables' }));
  fireEvent.change(screen.getByLabelText('processStatus'), { target: { value: 'transport_ready' } });

  fireEvent.click(screen.getByRole('tab', { name: 'Bindings' }));
  const steelAmountRow = screen.getByRole('row', { name: /steelAmount/i });
  fireEvent.click(within(steelAmountRow).getByRole('button', { name: 'Edit' }));
  const dialog = await screen.findByRole('dialog', { name: 'Edit Binding' });
  fireEvent.change(within(dialog).getByLabelText('Source'), { target: { value: 'factory_mqtt_v2' } });
  fireEvent.click(within(dialog).getByRole('button', { name: 'OK' }));
  await waitFor(() => {
    expect(screen.getByText('factory_mqtt_v2')).toBeInTheDocument();
  });

  fireEvent.click(screen.getByRole('button', { name: 'Save' }));

  await waitFor(() => {
    expect(screen.getByText('Saved')).toBeInTheDocument();
  });

  const updated = await instanceService.getById('ladle_001');
  expect(updated?.variables.processStatus).toBe('transport_ready');
  expect(updated?.bindings?.steelAmount?.source).toBe('factory_mqtt_v2');
});

test('shows not found when route modelId does not match instance modelId', async () => {
  renderInstanceDetail('/models/not-ladle/instances/ladle_001');

  expect(await screen.findByText('Instance not found')).toBeInTheDocument();
  expect(screen.queryByDisplayValue('1号钢包')).not.toBeInTheDocument();
});
