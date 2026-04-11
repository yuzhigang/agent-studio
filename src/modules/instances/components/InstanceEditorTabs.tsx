import { Form, Input, Tabs } from 'antd';
import type { AgentBinding, AgentInstance } from '@/types/domain/instance';
import { BindingTableEditor } from './BindingTableEditor';
import { RuntimeJsonPanel } from './RuntimeJsonPanel';

interface InstanceEditorTabsProps {
  instance: AgentInstance;
  jsonDrafts: Record<string, string>;
  jsonErrors: Record<string, string | null>;
  onMetadataChange: <K extends keyof AgentInstance['metadata']>(key: K, value: AgentInstance['metadata'][K]) => void;
  onFieldChange: (section: 'attributes' | 'variables', key: string, value: unknown) => void;
  onBindingsChange: (value: Record<string, AgentBinding>) => void;
  onRuntimeChange: (key: 'memory' | 'activeGoals' | 'currentPlan' | 'extensions', raw: string) => void;
}

export function InstanceEditorTabs({
  instance,
  jsonDrafts,
  jsonErrors,
  onMetadataChange,
  onFieldChange,
  onBindingsChange,
  onRuntimeChange,
}: InstanceEditorTabsProps) {
  const attributes = Object.entries(instance.attributes ?? {});
  const variables = Object.entries(instance.variables ?? {});

  return (
    <Tabs
      defaultActiveKey="basic"
      items={[
        {
          key: 'basic',
          label: 'Basic',
          children: (
            <Form layout="vertical">
              <Form.Item label="Name">
                <Input
                  aria-label="Name"
                  value={instance.metadata.name}
                  onChange={(event) => onMetadataChange('name', event.target.value)}
                />
              </Form.Item>
              <Form.Item label="Title">
                <Input
                  aria-label="Title"
                  value={instance.metadata.title}
                  onChange={(event) => onMetadataChange('title', event.target.value)}
                />
              </Form.Item>
              <Form.Item label="Description">
                <Input.TextArea
                  aria-label="Description"
                  value={instance.metadata.description ?? ''}
                  onChange={(event) => onMetadataChange('description', event.target.value)}
                />
              </Form.Item>
            </Form>
          ),
        },
        {
          key: 'attributes',
          label: 'Attributes',
          children: (
            <Form layout="vertical">
              {attributes.map(([key, value]) => (
                <Form.Item key={key} label={key}>
                  <Input
                    aria-label={key}
                    value={String(value ?? '')}
                    onChange={(event) => onFieldChange('attributes', key, event.target.value)}
                  />
                </Form.Item>
              ))}
            </Form>
          ),
        },
        {
          key: 'variables',
          label: 'Variables',
          children: (
            <Form layout="vertical">
              {variables.map(([key, value]) => (
                <Form.Item key={key} label={key}>
                  <Input
                    aria-label={key}
                    value={String(value ?? '')}
                    onChange={(event) => onFieldChange('variables', key, event.target.value)}
                  />
                </Form.Item>
              ))}
            </Form>
          ),
        },
        {
          key: 'bindings',
          label: 'Bindings',
          children: <BindingTableEditor value={instance.bindings ?? {}} onChange={onBindingsChange} />,
        },
        {
          key: 'runtime-json',
          label: 'Runtime JSON',
          children: (
            <RuntimeJsonPanel
              instance={instance}
              jsonDrafts={jsonDrafts}
              jsonErrors={jsonErrors}
              onChange={onRuntimeChange}
            />
          ),
        },
      ]}
    />
  );
}
