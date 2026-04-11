import { Button, Flex, Tag } from 'antd';

interface SaveActionsProps {
  dirty: boolean;
  saving?: boolean;
  onSave: () => void | Promise<void>;
  onReset: () => void;
}

export function SaveActions({ dirty, saving, onSave, onReset }: SaveActionsProps) {
  return (
    <Flex gap={12} align="center">
      <Tag color={dirty ? 'gold' : 'green'}>{dirty ? 'Unsaved changes' : 'Saved'}</Tag>
      <Button onClick={onReset} disabled={!dirty}>
        Reset
      </Button>
      <Button type="primary" onClick={onSave} loading={saving} disabled={!dirty}>
        Save
      </Button>
    </Flex>
  );
}
