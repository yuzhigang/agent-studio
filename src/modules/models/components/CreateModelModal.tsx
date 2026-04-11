import { Button, Form, Input, Modal } from 'antd';
import { useState } from 'react';
import type { AgentModel } from '@/types/domain/model';

interface CreateModelModalProps {
  existingNames: string[];
  onCreate: (model: AgentModel) => Promise<void> | void;
}

interface CreateModelFormValues {
  name: string;
  title: string;
  description?: string;
}

const MODEL_NAME_PATTERN = /^[A-Za-z0-9_-]+$/;

function normalizeName(value: string): string {
  return value.trim().toLowerCase();
}

export function CreateModelModal({ existingNames, onCreate }: CreateModelModalProps) {
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm<CreateModelFormValues>();
  const existingNameSet = new Set(existingNames.map(normalizeName));

  async function handleFinish(values: CreateModelFormValues) {
    setSubmitting(true);
    try {
      await onCreate({
        $schema: 'https://agent-studio.io/schema/v2',
        metadata: {
          name: values.name.trim(),
          title: values.title.trim(),
          description: values.description?.trim() || undefined,
        },
        attributes: {},
        variables: {},
      });
      form.resetFields();
      setOpen(false);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <Button type="primary" onClick={() => setOpen(true)}>
        New Model
      </Button>
      <Modal open={open} title="Create Model" onCancel={() => setOpen(false)} footer={null} destroyOnHidden>
        <Form form={form} layout="vertical" onFinish={handleFinish}>
          <Form.Item
            name="name"
            label="Name"
            rules={[
              { required: true, whitespace: true },
              {
                validator: async (_, value) => {
                  const name = typeof value === 'string' ? value.trim() : '';
                  if (!name) {
                    return;
                  }

                  if (!MODEL_NAME_PATTERN.test(name)) {
                    throw new Error('Name can only include letters, numbers, "_" and "-"');
                  }

                  if (existingNameSet.has(normalizeName(name))) {
                    throw new Error('Model name already exists');
                  }
                },
              },
            ]}
          >
            <Input aria-label="Name" />
          </Form.Item>
          <Form.Item name="title" label="Title" rules={[{ required: true, whitespace: true }]}>
            <Input aria-label="Title" />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <Input.TextArea aria-label="Description" />
          </Form.Item>
          <Button htmlType="submit" type="primary" loading={submitting}>
            Create
          </Button>
        </Form>
      </Modal>
    </>
  );
}
