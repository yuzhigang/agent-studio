import { beforeEach, expect, test } from 'vitest';
import { instanceService } from './instanceService';

beforeEach(() => {
  localStorage.clear();
});

test('lists instances by model id', async () => {
  const instances = await instanceService.listByModel('ladle');
  expect(instances[0].modelId).toBe('ladle');
});

test('updates and persists an instance', async () => {
  const instance = (await instanceService.listByModel('ladle'))[0];
  instance.variables.processStatus = 'updated_in_test';
  await instanceService.update(instance);

  const saved = await instanceService.getById(instance.id);
  expect(saved?.variables.processStatus).toBe('updated_in_test');
});

test('does not leak mutable seed references across rehydrate', async () => {
  const instances = await instanceService.listByModel('ladle');
  instances[0].modelId = 'tampered-model';

  localStorage.clear();

  const rehydratedInstances = await instanceService.listByModel('ladle');
  expect(rehydratedInstances[0].modelId).toBe('ladle');
});

test('preserves persisted empty array without reseeding', async () => {
  localStorage.setItem('agent-studio/instances/v1', '[]');

  const instances = await instanceService.listByModel('ladle');
  expect(instances).toEqual([]);
});

test('throws when updating a non-existent instance', async () => {
  const base = structuredClone((await instanceService.listByModel('ladle'))[0]);
  base.id = 'missing-instance';

  await expect(instanceService.update(base)).rejects.toThrow('Instance not found');

  const saved = await instanceService.getById('missing-instance');
  expect(saved).toBeNull();
});
