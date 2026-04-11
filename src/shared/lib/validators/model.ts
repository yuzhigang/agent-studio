const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const isNonEmptyString = (value: unknown): value is string =>
  typeof value === 'string' && value.trim().length > 0;

function validateDefinitionGroup(groupKey: 'attributes' | 'variables', rawGroup: unknown, errors: string[]): void {
  if (rawGroup === undefined) {
    return;
  }

  if (!isRecord(rawGroup)) {
    errors.push(`${groupKey} must be an object`);
    return;
  }

  for (const [name, rawDefinition] of Object.entries(rawGroup)) {
    if (!isRecord(rawDefinition)) {
      errors.push(`${groupKey}.${name} must be an object`);
      continue;
    }

    if (!isNonEmptyString(rawDefinition.title)) {
      errors.push(`${groupKey}.${name}.title is required`);
    }

    const minimum = rawDefinition.minimum;
    const maximum = rawDefinition.maximum;
    if (typeof minimum === 'number' && typeof maximum === 'number' && minimum > maximum) {
      errors.push(`${groupKey}.${name}.minimum must be less than or equal to maximum`);
    }
  }
}

export function validateModelDraft(model: unknown): string[] {
  const errors: string[] = [];

  const root = isRecord(model) ? model : {};
  const metadata = isRecord(root.metadata) ? root.metadata : {};

  if (!isNonEmptyString(metadata.name)) {
    errors.push('metadata.name is required');
  }

  if (!isNonEmptyString(metadata.title)) {
    errors.push('metadata.title is required');
  }

  validateDefinitionGroup('attributes', root.attributes, errors);
  validateDefinitionGroup('variables', root.variables, errors);

  return errors;
}
