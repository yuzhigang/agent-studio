import { seedInstances } from '@/mocks/data/seedInstances';
import { readStorage, writeStorage } from '@/shared/lib/storage';
import type { AgentInstance } from '@/types/domain/instance';

const INSTANCES_KEY = 'agent-studio/instances/v1';

function cloneInstances(instances: AgentInstance[]): AgentInstance[] {
  return structuredClone(instances);
}

function hydrateFromSeed(): AgentInstance[] {
  const seeded = cloneInstances(seedInstances);
  writeStorage(INSTANCES_KEY, seeded);
  return seeded;
}

function loadAll(): AgentInstance[] {
  const raw = localStorage.getItem(INSTANCES_KEY);
  if (raw === null) {
    return hydrateFromSeed();
  }

  return cloneInstances(readStorage<AgentInstance[]>(INSTANCES_KEY, []));
}

export const instanceRepository = {
  list(): AgentInstance[] {
    return loadAll();
  },
  getById(instanceId: string): AgentInstance | null {
    return loadAll().find((instance) => instance.id === instanceId) ?? null;
  },
  listByModel(modelId: string): AgentInstance[] {
    return loadAll().filter((instance) => instance.modelId === modelId);
  },
  saveAll(instances: AgentInstance[]): void {
    writeStorage(INSTANCES_KEY, cloneInstances(instances));
  },
  reset(): void {
    writeStorage(INSTANCES_KEY, cloneInstances(seedInstances));
  },
};
