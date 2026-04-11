import { Alert, Card, Descriptions, Spin } from 'antd';
import { useParams } from 'react-router-dom';
import { InstanceEditorTabs } from '@/modules/instances/components/InstanceEditorTabs';
import { useInstanceDetail } from '@/modules/instances/hooks/useInstanceDetail';
import { SaveActions } from '@/shared/components/SaveActions';

export function InstanceDetailPage() {
  const { modelId = '', instanceId = '' } = useParams();
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
  } = useInstanceDetail(modelId, instanceId);

  if (loading) {
    return <Spin />;
  }

  if (!draft) {
    return <Alert type="error" message="Instance not found" />;
  }

  return (
    <Card title={draft.metadata.title} extra={<SaveActions dirty={dirty} saving={saving} onSave={save} onReset={reset} />}>
      {Object.values(jsonErrors).some(Boolean) ? (
        <Alert type="warning" message="Fix JSON errors before saving." style={{ marginBottom: 16 }} />
      ) : null}
      <Descriptions size="small" column={3} style={{ marginBottom: 16 }}>
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
    </Card>
  );
}
