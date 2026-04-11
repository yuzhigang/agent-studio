import { beforeEach, expect, test } from 'vitest';
import { modelService } from './modelService';

beforeEach(() => {
  localStorage.clear();
});

test('loads seed models on first read', async () => {
  const models = await modelService.list();
  expect(models[0].metadata.name).toBe('ladle');
});

test('creates and persists a model', async () => {
  await modelService.create({
    ...structuredClone((await modelService.list())[0]),
    metadata: {
      ...structuredClone((await modelService.list())[0]).metadata,
      name: 'crane',
      title: 'Crane',
    },
  });

  const models = await modelService.list();
  expect(models.some((model) => model.metadata.name === 'crane')).toBe(true);
});

test('does not leak mutable seed references across rehydrate', async () => {
  const models = await modelService.list();
  models[0].metadata.name = 'tampered';

  localStorage.clear();

  const rehydratedModels = await modelService.list();
  expect(rehydratedModels[0].metadata.name).toBe('ladle');
});

test('preserves persisted empty array without reseeding', async () => {
  localStorage.setItem('agent-studio/models/v1', '[]');

  const models = await modelService.list();
  expect(models).toEqual([]);
});

test('throws when updating a non-existent model', async () => {
  const base = structuredClone((await modelService.list())[0]);
  base.metadata.name = 'missing-model';
  base.metadata.title = 'Missing Model';

  await expect(modelService.update(base)).rejects.toThrow('Model not found');

  const models = await modelService.list();
  expect(models.some((model) => model.metadata.name === 'missing-model')).toBe(false);
});
