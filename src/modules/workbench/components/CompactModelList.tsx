import { CreateModelModal } from '@/modules/models/components/CreateModelModal';
import type { AgentModel } from '@/types/domain/model';

interface CompactModelListProps {
  models: AgentModel[];
  selectedModelId: string | null;
  onSelect: (modelId: string) => void;
  onCreate: (model: AgentModel) => Promise<void> | void;
}

export function CompactModelList({ models, selectedModelId, onSelect, onCreate }: CompactModelListProps) {
  return (
    <section aria-label="Models">
      <header>
        <h2>Models</h2>
        <CreateModelModal existingNames={models.map((model) => model.metadata.name)} onCreate={onCreate} />
      </header>
      <div>
        {models.map((model) => (
          <button
            key={model.metadata.name}
            type="button"
            aria-pressed={model.metadata.name === selectedModelId}
            onClick={() => onSelect(model.metadata.name)}
          >
            <span>{model.metadata.title}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
