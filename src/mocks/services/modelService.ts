import { modelRepository } from '@/mocks/repository/modelRepository';
import type { AgentModel } from '@/types/domain/model';

const delay = (ms = 80) => new Promise((resolve) => setTimeout(resolve, ms));

export const modelService = {
  async list(): Promise<AgentModel[]> {
    await delay();
    return modelRepository.list();
  },
  async getByName(modelId: string): Promise<AgentModel | null> {
    await delay();
    return modelRepository.getByName(modelId);
  },
  async create(model: AgentModel): Promise<AgentModel> {
    await delay();
    const next = [...modelRepository.list(), model];
    modelRepository.saveAll(next);
    return model;
  },
  async update(model: AgentModel): Promise<AgentModel> {
    await delay();
    const current = modelRepository.list();
    const index = current.findIndex((item) => item.metadata.name === model.metadata.name);
    if (index === -1) {
      throw new Error(`Model not found: ${model.metadata.name}`);
    }

    const next = [...current];
    next[index] = model;
    modelRepository.saveAll(next);
    return model;
  },
  async reset(): Promise<void> {
    await delay();
    modelRepository.reset();
  },
};
