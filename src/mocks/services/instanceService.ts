import { instanceRepository } from '@/mocks/repository/instanceRepository';
import type { AgentInstance } from '@/types/domain/instance';

const delay = (ms = 80) => new Promise((resolve) => setTimeout(resolve, ms));

export const instanceService = {
  async listByModel(modelId: string): Promise<AgentInstance[]> {
    await delay();
    return instanceRepository.listByModel(modelId);
  },
  async getById(instanceId: string): Promise<AgentInstance | null> {
    await delay();
    return instanceRepository.getById(instanceId);
  },
  async create(instance: AgentInstance): Promise<AgentInstance> {
    await delay();
    const current = instanceRepository.list();
    if (current.some((item) => item.id === instance.id)) {
      throw new Error(`Instance ID already exists: ${instance.id}`);
    }

    const next = [...current, instance];
    instanceRepository.saveAll(next);
    return instance;
  },
  async update(instance: AgentInstance): Promise<AgentInstance> {
    await delay();
    const current = instanceRepository.list();
    const index = current.findIndex((item) => item.id === instance.id);
    if (index === -1) {
      throw new Error(`Instance not found: ${instance.id}`);
    }

    const next = [...current];
    next[index] = instance;
    instanceRepository.saveAll(next);
    return instance;
  },
  async reset(): Promise<void> {
    await delay();
    instanceRepository.reset();
  },
};
