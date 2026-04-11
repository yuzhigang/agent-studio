import { Alert, Card, Flex, Spin } from 'antd';
import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { instanceService } from '@/mocks/services/instanceService';
import { CreateInstanceModal } from '@/modules/instances/components/CreateInstanceModal';
import { InstanceListByModel } from '@/modules/instances/components/InstanceListByModel';
import { ModelEditorTabs } from '@/modules/models/components/ModelEditorTabs';
import { useModelDetail } from '@/modules/models/hooks/useModelDetail';
import { SaveActions } from '@/shared/components/SaveActions';
import { useUnsavedChangesGuard } from '@/shared/hooks/useUnsavedChangesGuard';
import type { AgentInstance } from '@/types/domain/instance';

export function ModelDetailPage() {
  const { modelId = '' } = useParams();
  const { loading, draft, dirty, saving, jsonErrors, jsonDrafts, save, reset, setMetadata, setDefinitions, updateJsonBlock } =
    useModelDetail(modelId);
  useUnsavedChangesGuard(dirty);
  const [instances, setInstances] = useState<AgentInstance[]>([]);
  const [instancesLoading, setInstancesLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setInstancesLoading(true);

    instanceService.listByModel(modelId).then((next) => {
      if (!active) {
        return;
      }

      setInstances(next);
      setInstancesLoading(false);
    });

    return () => {
      active = false;
    };
  }, [modelId]);

  if (loading) {
    return <Spin />;
  }

  if (!draft) {
    return <Alert type="error" message="Model not found" />;
  }

  return (
    <Flex vertical gap={16}>
      <Card title={draft.metadata.title} extra={<SaveActions dirty={dirty} saving={saving} onSave={save} onReset={reset} />}>
        {Object.values(jsonErrors).some(Boolean) ? (
          <Alert type="warning" message="Fix JSON errors before saving." style={{ marginBottom: 16 }} />
        ) : null}
        <ModelEditorTabs
          model={draft}
          jsonErrors={jsonErrors}
          jsonDrafts={jsonDrafts}
          nameDisabled
          onMetadataChange={setMetadata}
          onAttributesChange={(value) => setDefinitions('attributes', value)}
          onVariablesChange={(value) => setDefinitions('variables', value)}
          onJsonChange={updateJsonBlock}
        />
      </Card>
      <Card
        title="Instances"
        extra={
          <CreateInstanceModal
            model={draft}
            existingInstanceIds={instances.map((instance) => instance.id)}
            onCreate={async (instance) => {
              const saved = await instanceService.create(instance);
              setInstances((current) => [...current, saved]);
            }}
          />
        }
      >
        {instancesLoading ? <Spin /> : <InstanceListByModel modelId={draft.metadata.name} instances={instances} />}
      </Card>
    </Flex>
  );
}
