import type { AgentInstance } from '@/types/domain/instance';
import { WorkbenchPlaceholder } from '@/modules/workbench/components/WorkbenchPlaceholder';

interface CompactInstanceListProps {
  instances: AgentInstance[];
  selectedInstanceId: string | null;
  onSelect: (instanceId: string) => void;
}

export function CompactInstanceList({ instances, selectedInstanceId, onSelect }: CompactInstanceListProps) {
  if (instances.length === 0) {
    return <WorkbenchPlaceholder title="Instances" description="No instances yet" />;
  }

  return (
    <section aria-label="Instances">
      <header>
        <h2>Instances</h2>
      </header>
      <div>
        {instances.map((instance) => (
          <button
            key={instance.id}
            type="button"
            aria-pressed={instance.id === selectedInstanceId}
            onClick={() => onSelect(instance.id)}
          >
            <span>{instance.id}</span>
            <span>{instance.state}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
