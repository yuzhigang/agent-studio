import { render, screen, waitFor } from '@testing-library/react';
import { createMemoryRouter, RouterProvider, useNavigate, useParams } from 'react-router-dom';
import { beforeEach, test } from 'vitest';
import { instanceService } from '@/mocks/services/instanceService';
import { modelService } from '@/mocks/services/modelService';
import { CompactInstanceList } from '@/modules/workbench/components/CompactInstanceList';
import { CompactModelList } from '@/modules/workbench/components/CompactModelList';
import { ConfigWorkbench } from '@/modules/workbench/components/ConfigWorkbench';
import { WorkbenchPlaceholder } from '@/modules/workbench/components/WorkbenchPlaceholder';
import { useConfigWorkbench } from '@/modules/workbench/hooks/useConfigWorkbench';
import type { AgentModel } from '@/types/domain/model';

function WorkbenchHarness() {
  const { modelId = '', instanceId = '' } = useParams();
  const navigate = useNavigate();
  const { models, instances, selectedModel, selectedInstance, loading, createModel } = useConfigWorkbench(modelId, instanceId);

  if (loading) {
    return <span>Loading</span>;
  }

  const selectedModelId = selectedModel?.metadata.name ?? null;
  const selectedInstanceId = selectedInstance?.id ?? null;

  return (
    <section>
      <CompactModelList
        models={models}
        selectedModelId={selectedModelId}
        onSelect={(nextModelId) => {
          navigate(`/models/${nextModelId}`);
        }}
        onCreate={createModel}
      />
      <CompactInstanceList
        instances={instances}
        selectedInstanceId={selectedInstanceId}
        onSelect={(nextInstanceId) => {
          if (!selectedModelId) {
            return;
          }

          navigate(`/models/${selectedModelId}/instances/${nextInstanceId}`);
        }}
      />
      {selectedInstance ? (
        <section aria-label="Instance Detail">
          <h2>{selectedInstance.metadata.title}</h2>
        </section>
      ) : (
        <WorkbenchPlaceholder title="Instance Detail" description="Select an instance to edit" />
      )}
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

function RoutedConfigWorkbench() {
  const { modelId = '', instanceId = '' } = useParams();

  return <ConfigWorkbench modelIdParam={modelId} instanceIdParam={instanceId} />;
}

function renderRealWorkbench(pathname = '/models/ladle/instances/ladle_001') {
  const router = createMemoryRouter(
    [
      { path: '/models/:modelId', element: <RoutedConfigWorkbench /> },
      { path: '/models/:modelId/instances/:instanceId', element: <RoutedConfigWorkbench /> },
    ],
    { initialEntries: [pathname] },
  );

  render(<RouterProvider router={router} />);
}

beforeEach(async () => {
  localStorage.clear();
  await Promise.all([modelService.reset(), instanceService.reset()]);
});

async function createModel(model: AgentModel) {
  await modelService.create(model);
}

test('loads models and derives selected model/instance from route params', async () => {
  renderWorkbench('/models/ladle/instances/ladle_001');

  expect(await screen.findByRole('button', { name: '钢包智能体' })).toHaveAttribute('aria-pressed', 'true');
  expect(await screen.findByRole('button', { name: /ladle_001/i })).toHaveAttribute('aria-pressed', 'true');
});

test('does not preselect an instance when the route only targets a model', async () => {
  renderWorkbench('/models/ladle');

  expect(await screen.findByRole('button', { name: '钢包智能体' })).toHaveAttribute('aria-pressed', 'true');
  expect(await screen.findByRole('button', { name: /ladle_001/i })).toHaveAttribute('aria-pressed', 'false');
});

test('switches instance list when the selected model route changes', async () => {
  await createModel({
    $schema: 'https://agent-studio.io/schema/v2',
    metadata: {
      name: 'crane',
      title: '天车智能体',
    },
    attributes: {},
    variables: {},
  });

  renderWorkbench('/models/crane');

  expect(await screen.findByRole('button', { name: '天车智能体' })).toHaveAttribute('aria-pressed', 'true');
  expect(await screen.findByText('No instances yet')).toBeInTheDocument();
});

test('shows detail placeholder before an instance is selected', async () => {
  renderWorkbench('/models/ladle');

  await waitFor(() => {
    expect(screen.getByText('Select an instance to edit')).toBeInTheDocument();
  });
  expect(screen.queryByRole('heading', { name: '1号钢包' })).not.toBeInTheDocument();
});

test('renders the compact workbench structure with layout classes', async () => {
  renderRealWorkbench('/models/ladle/instances/ladle_001');

  const workbench = await screen.findByTestId('config-workbench');
  expect(workbench).toHaveClass('config-workbench');
  expect(workbench.querySelector('.workbench-pane--models')).not.toBeNull();
  expect(workbench.querySelector('.workbench-pane--instances')).not.toBeNull();
  expect(workbench.querySelector('.workbench-pane--detail')).not.toBeNull();
  expect(await screen.findByLabelText('Models')).toBeInTheDocument();
  expect(await screen.findByLabelText('Instances')).toBeInTheDocument();
  expect(await screen.findByLabelText('Instance Detail')).toBeInTheDocument();
});
