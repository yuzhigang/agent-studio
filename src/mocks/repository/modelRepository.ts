import { seedModels } from '@/mocks/data/seedModels';
import { readStorage, writeStorage } from '@/shared/lib/storage';
import type { AgentModel } from '@/types/domain/model';

const MODELS_KEY = 'agent-studio/models/v1';

function cloneModels(models: AgentModel[]): AgentModel[] {
  return structuredClone(models);
}

function hydrateFromSeed(): AgentModel[] {
  const seeded = cloneModels(seedModels);
  writeStorage(MODELS_KEY, seeded);
  return seeded;
}

function loadAll(): AgentModel[] {
  const raw = localStorage.getItem(MODELS_KEY);
  if (raw === null) {
    return hydrateFromSeed();
  }

  return cloneModels(readStorage<AgentModel[]>(MODELS_KEY, []));
}

export const modelRepository = {
  list(): AgentModel[] {
    return loadAll();
  },
  getByName(modelId: string): AgentModel | null {
    return loadAll().find((model) => model.metadata.name === modelId) ?? null;
  },
  saveAll(models: AgentModel[]): void {
    writeStorage(MODELS_KEY, cloneModels(models));
  },
  reset(): void {
    writeStorage(MODELS_KEY, cloneModels(seedModels));
  },
};
