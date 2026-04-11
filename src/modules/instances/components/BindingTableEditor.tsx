import { Button, Form, Input, Modal, Space, Table } from 'antd';
import { useMemo, useState } from 'react';
import { buildBindingRows } from '@/modules/instances/adapters/instanceAdapters';
import type { AgentBinding } from '@/types/domain/instance';

interface BindingTableEditorProps {
  value: Record<string, AgentBinding>;
  onChange: (value: Record<string, AgentBinding>) => void;
}

interface BindingFormValues {
  name: string;
  source: string;
  path?: string;
  topic?: string;
  selector?: string;
  transform?: string;
}

export function BindingTableEditor({ value, onChange }: BindingTableEditorProps) {
  const [open, setOpen] = useState(false);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [form] = Form.useForm<BindingFormValues>();
  const rows = useMemo(() => buildBindingRows(value), [value]);

  function openEditor(key?: string) {
    const nextKey = key ?? null;
    setEditingKey(nextKey);
    form.setFieldsValue(
      key
        ? {
            name: key,
            source: value[key]?.source ?? '',
            path: value[key]?.path,
            topic: value[key]?.topic,
            selector: value[key]?.selector,
            transform: value[key]?.transform,
          }
        : {
            name: '',
            source: '',
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
    const nextBinding: AgentBinding = {
      source: values.source.trim(),
      path: values.path?.trim() || undefined,
      topic: values.topic?.trim() || undefined,
      selector: values.selector?.trim() || undefined,
      transform: values.transform?.trim() || undefined,
    };

    onChange({
      ...value,
      [name]: nextBinding,
    });
    closeEditor();
  }

  return (
    <>
      <Space style={{ marginBottom: 12 }}>
        <strong>Bindings</strong>
        <Button onClick={() => openEditor()}>Add</Button>
      </Space>
      <Table
        rowKey="name"
        pagination={false}
        dataSource={rows}
        columns={[
          { title: 'Variable', dataIndex: 'name' },
          { title: 'Source', dataIndex: 'source' },
          { title: 'Selector', dataIndex: 'selector' },
          { title: 'Transform', dataIndex: 'transform' },
          {
            title: 'Action',
            render: (_, row: { name: string }) => (
              <Button size="small" onClick={() => openEditor(row.name)}>
                Edit
              </Button>
            ),
          },
        ]}
      />
      <Modal
        open={open}
        title={editingKey ? 'Edit Binding' : 'Add Binding'}
        onCancel={closeEditor}
        onOk={submit}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="Variable" rules={[{ required: true, whitespace: true }]}>
            <Input aria-label="Variable" readOnly={editingKey !== null} />
          </Form.Item>
          <Form.Item name="source" label="Source" rules={[{ required: true, whitespace: true }]}>
            <Input aria-label="Source" />
          </Form.Item>
          <Form.Item name="path" label="Path">
            <Input aria-label="Path" />
          </Form.Item>
          <Form.Item name="topic" label="Topic">
            <Input aria-label="Topic" />
          </Form.Item>
          <Form.Item name="selector" label="Selector">
            <Input aria-label="Selector" />
          </Form.Item>
          <Form.Item name="transform" label="Transform">
            <Input aria-label="Transform" />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
