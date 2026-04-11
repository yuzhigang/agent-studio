import { Alert, Card, Spin } from 'antd';
import { useParams } from 'react-router-dom';
import { ModelEditorTabs } from '@/modules/models/components/ModelEditorTabs';
import { useModelDetail } from '@/modules/models/hooks/useModelDetail';
import { SaveActions } from '@/shared/components/SaveActions';

export function ModelDetailPage() {
  const { modelId = '' } = useParams();
  const { loading, draft, dirty, saving, jsonErrors, jsonDrafts, save, reset, setMetadata, setDefinitions, updateJsonBlock } =
    useModelDetail(modelId);

  if (loading) {
    return <Spin />;
  }

  if (!draft) {
    return <Alert type="error" message="Model not found" />;
  }

  return (
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
  );
}
