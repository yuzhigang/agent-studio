import { Button, Form, Input, InputNumber, Modal, Select, Space, Switch, Table } from 'antd';
import { useMemo, useState } from 'react';
import { buildDefinitionRows } from '@/modules/models/adapters/modelAdapters';
import type { AgentFieldDefinition } from '@/types/domain/model';

interface DefinitionTableEditorProps {
  label: string;
  value: Record<string, AgentFieldDefinition>;
  onChange: (value: Record<string, AgentFieldDefinition>) => void;
}

interface DefinitionFormValues {
  name: string;
  title: string;
  type: string;
  description?: string;
  minimum?: number;
  maximum?: number;
  nullable?: boolean;
}

export function DefinitionTableEditor({ label, value, onChange }: DefinitionTableEditorProps) {
  const [open, setOpen] = useState(false);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [form] = Form.useForm<DefinitionFormValues>();
  const rows = useMemo(() => buildDefinitionRows(value), [value]);

  function openEditor(key?: string) {
    const nextKey = key ?? null;
    setEditingKey(nextKey);
    form.setFieldsValue(
      key
        ? {
            name: key,
            title: value[key].title,
            type: value[key].type,
            description: value[key].description,
            minimum: value[key].minimum,
            maximum: value[key].maximum,
            nullable: value[key].nullable,
          }
        : {
            name: '',
            title: '',
            type: 'string',
            nullable: false,
          },
    );
    setOpen(true);
  }

  function closeEditor() {
    setOpen(false);
    setEditingKey(null);
    form.resetFields();
  }

  async function submit() {
    const values = await form.validateFields();
    const name = values.name.trim();
    const nextValue: AgentFieldDefinition = {
      type: values.type,
      title: values.title.trim(),
      description: values.description?.trim() || undefined,
      minimum: values.minimum,
      maximum: values.maximum,
      nullable: values.nullable,
    };

    onChange({
      ...value,
      [name]: nextValue,
    });
    closeEditor();
  }

  return (
    <>
      <Space style={{ marginBottom: 12 }}>
        <strong>{label}</strong>
        <Button onClick={() => openEditor()}>Add</Button>
      </Space>
      <Table
        rowKey="key"
        pagination={false}
        dataSource={rows}
        columns={[
          { title: 'Name', dataIndex: 'key' },
          { title: 'Title', dataIndex: 'title' },
          { title: 'Type', dataIndex: 'type' },
          { title: 'Nullable', dataIndex: 'nullable', render: (flag: boolean | undefined) => (flag ? 'Yes' : 'No') },
          {
            title: 'Action',
            render: (_, row: { key: string }) => (
              <Button size="small" onClick={() => openEditor(row.key)}>
                Edit
              </Button>
            ),
          },
        ]}
      />
      <Modal open={open} title={editingKey ? 'Edit Definition' : 'Add Definition'} onCancel={closeEditor} onOk={submit}>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="Name" rules={[{ required: true, whitespace: true }]}>
            <Input aria-label="Definition Name" disabled={editingKey !== null} />
          </Form.Item>
          <Form.Item name="title" label="Title" rules={[{ required: true, whitespace: true }]}>
            <Input aria-label="Definition Title" />
          </Form.Item>
          <Form.Item name="type" label="Type" rules={[{ required: true }]}>
            <Select
              options={[
                { value: 'string', label: 'string' },
                { value: 'number', label: 'number' },
                { value: 'integer', label: 'integer' },
                { value: 'boolean', label: 'boolean' },
              ]}
            />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <Input.TextArea />
          </Form.Item>
          <Form.Item name="minimum" label="Minimum">
            <InputNumber style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="maximum" label="Maximum">
            <InputNumber style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="nullable" label="Nullable" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
