import { Alert, Input } from 'antd';

interface JsonBlockEditorProps {
  label: string;
  value: string;
  error?: string | null;
  onChange: (value: string) => void;
}

export function JsonBlockEditor({ label, value, error, onChange }: JsonBlockEditorProps) {
  return (
    <>
      {error ? <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} /> : null}
      <Input.TextArea
        aria-label={label}
        autoSize={{ minRows: 10 }}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </>
  );
}
