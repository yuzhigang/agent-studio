import { useEffect, useState } from 'react';
import { instanceService } from '@/mocks/services/instanceService';
import { modelService } from '@/mocks/services/modelService';
import type { AgentInstance } from '@/types/domain/instance';
import type { AgentModel } from '@/types/domain/model';

export function useConfigWorkbench(modelIdParam?: string, instanceIdParam?: string) {
  const [models, setModels] = useState<AgentModel[]>([]);
  const [instances, setInstances] = useState<AgentInstance[]>([]);
  const [loadingModels, setLoadingModels] = useState(true);
  const [loadingInstances, setLoadingInstances] = useState(true);

  const selectedModel = models.find((model) => model.metadata.name === modelIdParam) ?? models[0] ?? null;
  const selectedInstance = instances.find((instance) => instance.id === instanceIdParam) ?? instances[0] ?? null;

  useEffect(() => {
    let active = true;

    modelService.list().then((next) => {
      if (!active) {
        return;
      }

      setModels(next);
      setLoadingModels(false);
    });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    const selectedModelId = selectedModel?.metadata.name;

    if (!selectedModelId) {
      setInstances([]);
      setLoadingInstances(false);
      return () => {
        active = false;
      };
    }

    setLoadingInstances(true);
    instanceService.listByModel(selectedModelId).then((next) => {
      if (!active) {
        return;
      }

      setInstances(next);
      setLoadingInstances(false);
    });

    return () => {
      active = false;
    };
  }, [selectedModel?.metadata.name]);

  async function createModel(model: AgentModel) {
    const saved = await modelService.create(model);
    setModels((current) => [...current, saved]);
  }

  async function createInstance(instance: AgentInstance) {
    const saved = await instanceService.create(instance);
    if (saved.modelId === selectedModel?.metadata.name) {
      setInstances((current) => [...current, saved]);
    }
  }

  return {
    models,
    instances,
    loading: loadingModels || loadingInstances,
    selectedModel,
    selectedInstance,
    createModel,
    createInstance,
  };
}
