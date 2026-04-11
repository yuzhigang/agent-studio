import { Divider, Tabs, Typography } from 'antd';
import { buildModelJsonBlocks } from '@/modules/models/adapters/modelAdapters';
import { JsonBlockEditor } from '@/shared/components/JsonBlockEditor';
import type { AgentModel } from '@/types/domain/model';
import { DefinitionTableEditor } from './DefinitionTableEditor';
import { ModelMetadataForm } from './ModelMetadataForm';

interface ModelEditorTabsProps {
  model: AgentModel;
  jsonErrors: Record<string, string | null>;
  jsonDrafts: Record<string, string>;
  nameDisabled?: boolean;
  onMetadataChange: <K extends keyof AgentModel['metadata']>(key: K, value: AgentModel['metadata'][K]) => void;
  onAttributesChange: (value: AgentModel['attributes']) => void;
  onVariablesChange: (value: AgentModel['variables']) => void;
  onJsonChange: (key: keyof AgentModel, value: string) => void;
}

export function ModelEditorTabs({
  model,
  jsonErrors,
  jsonDrafts,
  nameDisabled = false,
  onMetadataChange,
  onAttributesChange,
  onVariablesChange,
  onJsonChange,
}: ModelEditorTabsProps) {
  const jsonBlocks = buildModelJsonBlocks(model);

  return (
    <Tabs
      defaultActiveKey="basic"
      items={[
        {
          key: 'basic',
          label: 'Basic',
          children: <ModelMetadataForm value={model.metadata} nameDisabled={nameDisabled} onChange={onMetadataChange} />,
        },
        {
          key: 'attributes',
          label: 'Attributes',
          children: <DefinitionTableEditor label="Attributes" value={model.attributes} onChange={onAttributesChange} />,
        },
        {
          key: 'variables',
          label: 'Variables',
          children: <DefinitionTableEditor label="Variables" value={model.variables} onChange={onVariablesChange} />,
        },
        {
          key: 'advanced-json',
          label: 'Advanced JSON',
          children: (
            <>
              {jsonBlocks.map((block, index) => (
                <div key={block.key} style={{ marginBottom: 20 }}>
                  <Typography.Text strong>{block.label}</Typography.Text>
                  <JsonBlockEditor
                    label={block.label}
                    value={jsonDrafts[block.key] ?? ''}
                    error={jsonErrors[block.key] ?? null}
                    onChange={(value) => onJsonChange(block.key as keyof AgentModel, value)}
                  />
                  {index < jsonBlocks.length - 1 ? <Divider style={{ marginTop: 16 }} /> : null}
                </div>
              ))}
            </>
          ),
        },
      ]}
    />
  );
}
