import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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
  await Promise.all([modelService.reset(), instanceService.reset()]);
});

test('hydrates model and instance selections from the workbench route', async () => {
  renderModelsWorkbench('/models/ladle/instances/ladle_001');

  await screen.findByRole('button', { name: '钢包智能体' });
  await screen.findByDisplayValue('1号钢包');
  expect(screen.getByRole('button', { name: '钢包智能体' })).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByRole('button', { name: /ladle_001/i })).toHaveAttribute('aria-pressed', 'true');
});

test('switches to the selected model route and clears instance selection', async () => {
  await modelService.create({
    $schema: 'https://agent-studio.io/schema/v2',
    metadata: {
      name: 'crane',
      title: '天车智能体',
    },
    attributes: {},
    variables: {},
  });
  const user = userEvent.setup();
  const router = renderModelsWorkbench('/models/ladle/instances/ladle_001');

  await user.click(await screen.findByRole('button', { name: '天车智能体' }));

  await waitFor(() => {
    expect(router.state.location.pathname).toBe('/models/crane');
  });
  await screen.findByText('No instances yet');
  await screen.findByText('Select an instance to edit');
});
