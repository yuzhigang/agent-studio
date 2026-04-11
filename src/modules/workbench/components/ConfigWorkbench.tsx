import { Flex, Spin } from 'antd';
import { useNavigate } from 'react-router-dom';
import { CreateInstanceModal } from '@/modules/instances/components/CreateInstanceModal';
import { CompactInstanceList } from '@/modules/workbench/components/CompactInstanceList';
import { CompactModelList } from '@/modules/workbench/components/CompactModelList';
import { InstanceDetailWorkbench } from '@/modules/workbench/components/InstanceDetailWorkbench';
import { WorkbenchPlaceholder } from '@/modules/workbench/components/WorkbenchPlaceholder';
import { useConfigWorkbench } from '@/modules/workbench/hooks/useConfigWorkbench';

interface ConfigWorkbenchProps {
  modelIdParam?: string;
  instanceIdParam?: string;
}

export function ConfigWorkbench({ modelIdParam, instanceIdParam }: ConfigWorkbenchProps) {
  const navigate = useNavigate();
  const { models, instances, loading, selectedModel, selectedInstance, createModel, createInstance } = useConfigWorkbench(
    modelIdParam,
    instanceIdParam,
  );
  const selectedModelId = selectedModel?.metadata.name ?? null;
  const selectedInstanceId = selectedInstance?.id ?? null;
  const routeModelId = modelIdParam ? modelIdParam : null;
  const routeInstanceId = instanceIdParam ? instanceIdParam : null;

  if (loading) {
    return <Spin />;
  }

  return (
    <section
      data-testid="config-workbench"
      style={{ display: 'grid', gridTemplateColumns: '240px 260px minmax(0, 1fr)', gap: 12, alignItems: 'start' }}
    >
      <CompactModelList
        models={models}
        selectedModelId={selectedModelId}
        onSelect={(nextModelId) => {
          navigate(`/models/${nextModelId}`);
        }}
        onCreate={createModel}
      />

      <section aria-label="Instances Pane">
        <Flex justify="end" style={{ marginBottom: 8 }}>
          {selectedModel ? (
            <CreateInstanceModal
              model={selectedModel}
              existingInstanceIds={instances.map((instance) => instance.id)}
              onCreate={async (instance) => {
                await createInstance(instance);
                navigate(`/models/${instance.modelId}/instances/${instance.id}`);
              }}
            />
          ) : null}
        </Flex>
        {selectedModel ? (
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
        ) : (
          <WorkbenchPlaceholder title="Instances" description="Select a model first" />
        )}
      </section>

      <InstanceDetailWorkbench modelId={routeModelId} instanceId={routeInstanceId} />
    </section>
  );
}
