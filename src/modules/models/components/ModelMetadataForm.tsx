import { Form, Input } from 'antd';
import type { AgentModelMetadata } from '@/types/domain/model';

interface ModelMetadataFormProps {
  value: AgentModelMetadata;
  nameDisabled?: boolean;
  onChange: <K extends keyof AgentModelMetadata>(key: K, value: AgentModelMetadata[K]) => void;
}

export function ModelMetadataForm({ value, nameDisabled = false, onChange }: ModelMetadataFormProps) {
  return (
    <Form layout="vertical">
      <Form.Item label="Name">
        <Input
          aria-label="Name"
          value={value.name}
          disabled={nameDisabled}
          onChange={(event) => onChange('name', event.target.value)}
        />
      </Form.Item>
      <Form.Item label="Title">
        <Input aria-label="Title" value={value.title} onChange={(event) => onChange('title', event.target.value)} />
      </Form.Item>
      <Form.Item label="Description">
        <Input.TextArea
          aria-label="Description"
          value={value.description}
          onChange={(event) => onChange('description', event.target.value)}
        />
      </Form.Item>
    </Form>
  );
}
