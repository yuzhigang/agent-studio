import type { AgentFieldDefinition, AgentModel } from '@/types/domain/model';
import type { DefinitionTableRow, JsonBlockConfig } from '@/types/ui/editor';

export function buildDefinitionRows(definitions: Record<string, AgentFieldDefinition>): DefinitionTableRow[] {
  return Object.entries(definitions).map(([key, value]) => ({
    key,
    title: value.title,
    type: value.type,
    description: value.description,
    defaultValue: value.default,
    nullable: value.nullable,
  }));
}

export function buildModelJsonBlocks(model: AgentModel): JsonBlockConfig[] {
  return [
    ['derivedProperties', 'Derived Properties'],
    ['rules', 'Rules'],
    ['functions', 'Functions'],
    ['services', 'Services'],
    ['states', 'States'],
    ['transitions', 'Transitions'],
    ['behaviors', 'Behaviors'],
    ['events', 'Events'],
    ['alarms', 'Alarms'],
    ['schedules', 'Schedules'],
    ['goals', 'Goals'],
    ['decisionPolicies', 'Decision Policies'],
    ['memory', 'Memory'],
    ['plans', 'Plans'],
  ].map(([key, label]) => ({
    key,
    label,
    value: model[key as keyof AgentModel],
  }));
}
