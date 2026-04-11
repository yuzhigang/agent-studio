import { seedInstances } from '@/mocks/data/seedInstances';
import { buildBindingRows, buildRuntimeJsonBlocks } from './instanceAdapters';
import { validateInstanceDraft } from '@/shared/lib/validators/instance';
import type { AgentInstance } from '@/types/domain/instance';

test('builds binding rows from the seed instance', () => {
  const instance = seedInstances[0];
  const rows = buildBindingRows(instance.bindings);

  expect(rows.some((row) => row.name === 'temperature')).toBe(true);
});

test('rejects an instance without state', () => {
  const instance = structuredClone(seedInstances[0]);
  instance.state = '';

  expect(validateInstanceDraft(instance)).toContain('state is required');
});

test('exposes runtime JSON blocks', () => {
  const blocks = buildRuntimeJsonBlocks(seedInstances[0]);
  expect(blocks.map((block) => block.key)).toEqual(['memory', 'activeGoals', 'currentPlan', 'extensions']);
});

test('returns validation errors for malformed instance payload instead of throwing', () => {
  const malformedInstance = {
    id: null,
    modelId: 42,
    state: true,
    metadata: null,
    variables: 'invalid',
  };

  expect(() => validateInstanceDraft(malformedInstance)).not.toThrow();
  expect(validateInstanceDraft(malformedInstance)).toEqual(
    expect.arrayContaining([
      'id is required',
      'modelId is required',
      'state is required',
      'metadata.name is required',
      'metadata.title is required',
      'variables must be an object',
    ]),
  );
});

test('supports schema-optional bindings when building binding rows', () => {
  const instanceWithoutBindings: AgentInstance = {
    $schema: 'https://agent-studio.io/schema/v2/instance',
    id: 'ladle_partial',
    modelId: 'ladle',
    state: 'idle',
    metadata: {
      name: 'ladle_partial',
      title: 'Partial Ladle',
    },
    variables: {},
  };

  expect(validateInstanceDraft(instanceWithoutBindings)).toEqual([]);
  expect(buildBindingRows(instanceWithoutBindings.bindings)).toEqual([]);
});
