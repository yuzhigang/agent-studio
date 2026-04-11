import { useEffect, useState } from 'react';
import { modelService } from '@/mocks/services/modelService';
import type { AgentModel } from '@/types/domain/model';

export function useModelsPage() {
  const [models, setModels] = useState<AgentModel[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;

    modelService.list().then((next) => {
      if (!active) {
        return;
      }

      setModels(next);
      setLoading(false);
    });

    return () => {
      active = false;
    };
  }, []);

  async function createModel(model: AgentModel) {
    const saved = await modelService.create(model);
    setModels((current) => [...current, saved]);
  }

  return {
    models,
    loading,
    createModel,
  };
}
