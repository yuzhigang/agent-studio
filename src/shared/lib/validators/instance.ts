const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const isNonEmptyString = (value: unknown): value is string =>
  typeof value === 'string' && value.trim().length > 0;

export function validateInstanceDraft(instance: unknown): string[] {
  const errors: string[] = [];
  const root = isRecord(instance) ? instance : {};
  const metadata = isRecord(root.metadata) ? root.metadata : {};

  if (!isNonEmptyString(root.id)) {
    errors.push('id is required');
  }
  if (!isNonEmptyString(root.modelId)) {
    errors.push('modelId is required');
  }
  if (!isNonEmptyString(root.state)) {
    errors.push('state is required');
  }
  if (!isNonEmptyString(metadata.name)) {
    errors.push('metadata.name is required');
  }
  if (!isNonEmptyString(metadata.title)) {
    errors.push('metadata.title is required');
  }
  if (!isRecord(root.variables)) {
    errors.push('variables must be an object');
  }
  if (root.attributes !== undefined && !isRecord(root.attributes)) {
    errors.push('attributes must be an object');
  }
  if (root.bindings !== undefined && !isRecord(root.bindings)) {
    errors.push('bindings must be an object');
  }

  return errors;
}
