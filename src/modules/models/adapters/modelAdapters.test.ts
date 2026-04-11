import { seedModels } from '@/mocks/data/seedModels';
import { buildDefinitionRows, buildModelJsonBlocks } from './modelAdapters';
import { validateModelDraft } from '@/shared/lib/validators/model';

test('builds definition rows from the seed model', () => {
  const model = seedModels[0];
  const rows = buildDefinitionRows(model.attributes);

  expect(rows[0].key).toBe('capacity');
  expect(rows[0].title).toBe('容量');
});

test('rejects a model without metadata title', () => {
  const model = structuredClone(seedModels[0]);
  model.metadata.title = '';

  expect(validateModelDraft(model)).toContain('metadata.title is required');
});

test('exposes advanced model JSON blocks', () => {
  const blocks = buildModelJsonBlocks(seedModels[0]);
  expect(blocks.map((block) => block.key)).toContain('rules');
  expect(blocks.map((block) => block.key)).toContain('plans');
});

test('returns validation errors for malformed model payload instead of throwing', () => {
  const malformedModel = {
    metadata: null,
    attributes: {
      capacity: 'invalid-definition',
    },
    variables: null,
  };

  expect(() => validateModelDraft(malformedModel)).not.toThrow();
  expect(validateModelDraft(malformedModel)).toEqual(
    expect.arrayContaining([
      'metadata.name is required',
      'metadata.title is required',
      'attributes.capacity must be an object',
      'variables must be an object',
    ]),
  );
});
