import { Divider, Typography } from 'antd';
import { buildRuntimeJsonBlocks } from '@/modules/instances/adapters/instanceAdapters';
import { JsonBlockEditor } from '@/shared/components/JsonBlockEditor';
import type { AgentInstance } from '@/types/domain/instance';

interface RuntimeJsonPanelProps {
  instance: AgentInstance;
  jsonDrafts: Record<string, string>;
  jsonErrors: Record<string, string | null>;
  onChange: (key: 'memory' | 'activeGoals' | 'currentPlan' | 'extensions', raw: string) => void;
}

export function RuntimeJsonPanel({ instance, jsonDrafts, jsonErrors, onChange }: RuntimeJsonPanelProps) {
  return (
    <>
      {buildRuntimeJsonBlocks(instance).map((block, index) => (
        <div key={block.key} style={{ marginBottom: 20 }}>
          <Typography.Text strong>{block.label}</Typography.Text>
          <JsonBlockEditor
            label={block.label}
            value={jsonDrafts[block.key] ?? ''}
            error={jsonErrors[block.key] ?? null}
            onChange={(raw) => onChange(block.key as 'memory' | 'activeGoals' | 'currentPlan' | 'extensions', raw)}
          />
          {index < 3 ? <Divider style={{ marginTop: 16 }} /> : null}
        </div>
      ))}
    </>
  );
}
