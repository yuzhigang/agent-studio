import type { AgentBinding, AgentInstance } from '@/types/domain/instance';
import type { BindingTableRow, JsonBlockConfig } from '@/types/ui/editor';

export function buildBindingRows(bindings?: Record<string, AgentBinding>): BindingTableRow[] {
  return Object.entries(bindings ?? {}).map(([name, binding]) => ({
    name,
    ...binding,
  }));
}

export function buildRuntimeJsonBlocks(instance: AgentInstance): JsonBlockConfig[] {
  return [
    { key: 'memory', label: 'Memory', value: instance.memory ?? {} },
    { key: 'activeGoals', label: 'Active Goals', value: instance.activeGoals ?? [] },
    { key: 'currentPlan', label: 'Current Plan', value: instance.currentPlan ?? {} },
    { key: 'extensions', label: 'Extensions', value: instance.extensions ?? {} },
  ];
}
