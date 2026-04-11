import { Button, Form, Input, Modal, Select, message } from 'antd';
import { useMemo, useState } from 'react';
import { validateInstanceDraft } from '@/shared/lib/validators/instance';
import type { AgentInstance } from '@/types/domain/instance';
import type { AgentModel } from '@/types/domain/model';

interface CreateInstanceModalProps {
  model: AgentModel;
  existingInstanceIds: string[];
  onCreate: (instance: AgentInstance) => Promise<void> | void;
}

interface CreateInstanceFormValues {
  id: string;
  title: string;
  state: string;
}

const INSTANCE_ID_PATTERN = /^[A-Za-z0-9_-]+$/;

function normalizeId(value: string): string {
  return value.trim().toLowerCase();
}

export function CreateInstanceModal({ model, existingInstanceIds, onCreate }: CreateInstanceModalProps) {
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm<CreateInstanceFormValues>();
  const existingIdSet = new Set(existingInstanceIds.map(normalizeId));
  const stateOptions = useMemo(() => Object.keys(model.states ?? {}), [model.states]);

  function buildInstance(values: CreateInstanceFormValues): AgentInstance {
    return {
      $schema: 'https://agent-studio.io/schema/v2/instance',
      id: values.id.trim(),
      modelId: model.metadata.name,
      state: values.state,
      metadata: {
        name: values.id.trim(),
        title: values.title.trim(),
      },
      attributes: Object.fromEntries(
        Object.entries(model.attributes).map(([key, definition]) => [key, definition.default ?? null]),
      ),
      variables: Object.fromEntries(
        Object.entries(model.variables).map(([key, definition]) => [key, definition.default ?? null]),
      ),
      bindings: {},
      memory: {},
      activeGoals: [],
      currentPlan: {},
      extensions: {},
    };
  }

  async function handleFinish(values: CreateInstanceFormValues) {
    const nextInstance = buildInstance(values);
    const errors = validateInstanceDraft(nextInstance);
    if (errors.length > 0) {
      message.error(errors[0]);
      return;
    }

    setSubmitting(true);
    try {
      await onCreate(nextInstance);
      form.resetFields();
      setOpen(false);
    } catch (error) {
      const reason = error instanceof Error ? error.message : 'Failed to create instance';
      message.error(reason);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <Button onClick={() => setOpen(true)}>New Instance</Button>
      <Modal open={open} title="Create Instance" onCancel={() => setOpen(false)} footer={null} destroyOnHidden>
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            state: stateOptions[0] ?? 'initialized',
          }}
          onFinish={handleFinish}
        >
          <Form.Item
            name="id"
            label="Instance ID"
            rules={[
              { required: true, whitespace: true },
              {
                validator: async (_, value) => {
                  const id = typeof value === 'string' ? value.trim() : '';
                  if (!id) {
                    return;
                  }

                  if (!INSTANCE_ID_PATTERN.test(id)) {
                    throw new Error('Instance ID can only include letters, numbers, "_" and "-"');
                  }

                  if (existingIdSet.has(normalizeId(id))) {
                    throw new Error('Instance ID already exists');
                  }
                },
              },
            ]}
          >
            <Input aria-label="Instance ID" />
          </Form.Item>
          <Form.Item name="title" label="Title" rules={[{ required: true, whitespace: true }]}>
            <Input aria-label="Title" />
          </Form.Item>
          <Form.Item name="state" label="State" rules={[{ required: true }]}>
            <Select
              options={(stateOptions.length > 0 ? stateOptions : ['initialized']).map((value) => ({
                label: value,
                value,
              }))}
            />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={submitting}>
            Create
          </Button>
        </Form>
      </Modal>
    </>
  );
}
