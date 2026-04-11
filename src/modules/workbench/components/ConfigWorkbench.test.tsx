import { render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider, useParams } from 'react-router-dom';
import { beforeEach, test } from 'vitest';
import { instanceService } from '@/mocks/services/instanceService';
import { modelService } from '@/mocks/services/modelService';
import { useConfigWorkbench } from '@/modules/workbench/hooks/useConfigWorkbench';

function WorkbenchHarness() {
  const { modelId = '', instanceId = '' } = useParams();
  const { models, instances, selectedModel, selectedInstance, loading } = useConfigWorkbench(modelId, instanceId);

  if (loading) {
    return <span>Loading</span>;
  }

  return (
    <section>
      <h1>Models</h1>
      <div>
        {models.map((model) => (
          <button
            key={model.metadata.name}
            type="button"
            aria-pressed={model.metadata.name === selectedModel?.metadata.name}
          >
            {model.metadata.title}
          </button>
        ))}
      </div>
      <div>
        {instances.map((instance) => (
          <button key={instance.id} type="button" aria-pressed={instance.id === selectedInstance?.id}>
            {instance.id}
          </button>
        ))}
      </div>
    </section>
  );
}

function renderWorkbench(pathname = '/models/ladle/instances/ladle_001') {
  const router = createMemoryRouter(
    [
      { path: '/models/:modelId', element: <WorkbenchHarness /> },
      { path: '/models/:modelId/instances/:instanceId', element: <WorkbenchHarness /> },
    ],
    { initialEntries: [pathname] },
  );

  render(<RouterProvider router={router} />);
}

beforeEach(async () => {
  localStorage.clear();
  await Promise.all([modelService.reset(), instanceService.reset()]);
});

test('loads models and derives selected model/instance from route params', async () => {
  renderWorkbench('/models/ladle/instances/ladle_001');

  expect(await screen.findByRole('heading', { name: 'Models' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '钢包智能体' })).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByRole('button', { name: 'ladle_001' })).toHaveAttribute('aria-pressed', 'true');
});

test('does not preselect an instance when the route only targets a model', async () => {
  renderWorkbench('/models/ladle');

  expect(await screen.findByRole('heading', { name: 'Models' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '钢包智能体' })).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByRole('button', { name: 'ladle_001' })).toHaveAttribute('aria-pressed', 'false');
});
