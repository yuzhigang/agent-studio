import { Alert, Descriptions, Spin } from 'antd';
import { InstanceEditorTabs } from '@/modules/instances/components/InstanceEditorTabs';
import { useInstanceDetail } from '@/modules/instances/hooks/useInstanceDetail';
import { WorkbenchPlaceholder } from '@/modules/workbench/components/WorkbenchPlaceholder';
import { SaveActions } from '@/shared/components/SaveActions';
import { useUnsavedChangesGuard } from '@/shared/hooks/useUnsavedChangesGuard';

interface InstanceDetailWorkbenchProps {
  modelId: string | null;
  instanceId: string | null;
}

export function InstanceDetailWorkbench({ modelId, instanceId }: InstanceDetailWorkbenchProps) {
  const scopedModelId = modelId ?? '';
  const scopedInstanceId = instanceId ?? '';
  const {
    loading,
    draft,
    dirty,
    saving,
    jsonErrors,
    jsonDrafts,
    save,
    reset,
    updateMetadata,
    updateField,
    updateBindings,
    updateRuntimeBlock,
  } = useInstanceDetail(scopedModelId, scopedInstanceId);
  useUnsavedChangesGuard(Boolean(instanceId) && dirty);

  if (!modelId || !instanceId) {
    return <WorkbenchPlaceholder title="Instance Detail" description="Select an instance to edit" />;
  }

  if (loading) {
    return (
      <section aria-label="Instance Detail">
        <h2>Instance Detail</h2>
        <Spin />
      </section>
    );
  }

  if (!draft) {
    return (
      <section aria-label="Instance Detail">
        <h2>Instance Detail</h2>
        <Alert type="error" message="Instance not found" />
      </section>
    );
  }

  return (
    <section aria-label="Instance Detail">
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <div>
          <h2 style={{ margin: 0 }}>{draft.metadata.title}</h2>
          <p style={{ margin: '4px 0 0', color: '#4f5b67' }}>
            {draft.modelId} / {draft.state}
          </p>
        </div>
        <SaveActions dirty={dirty} saving={saving} onSave={save} onReset={reset} />
      </header>
      {Object.values(jsonErrors).some(Boolean) ? (
        <Alert type="warning" message="Fix JSON errors before saving." style={{ marginBottom: 12 }} />
      ) : null}
      <Descriptions size="small" column={3} style={{ marginBottom: 12 }}>
        <Descriptions.Item label="Instance ID">{draft.id}</Descriptions.Item>
        <Descriptions.Item label="Model">{draft.modelId}</Descriptions.Item>
        <Descriptions.Item label="State">{draft.state}</Descriptions.Item>
      </Descriptions>
      <InstanceEditorTabs
        instance={draft}
        jsonDrafts={jsonDrafts}
        jsonErrors={jsonErrors}
        onMetadataChange={updateMetadata}
        onFieldChange={updateField}
        onBindingsChange={updateBindings}
        onRuntimeChange={updateRuntimeBlock}
      />
    </section>
  );
}
