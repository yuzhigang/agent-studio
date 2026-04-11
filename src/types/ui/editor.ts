export interface DefinitionTableRow {
  key: string;
  title: string;
  type: string;
  description?: string;
  defaultValue?: unknown;
  nullable?: boolean;
}

export interface BindingTableRow {
  name: string;
  source: string;
  path?: string;
  topic?: string;
  selector?: string;
  transform?: string;
  refreshSeconds?: number;
}

export interface JsonBlockConfig {
  key: string;
  label: string;
  value: unknown;
}

export type ModelEditorTabKey = 'basic' | 'attributes' | 'variables' | 'advanced-json';
export type InstanceEditorTabKey = 'basic' | 'attributes' | 'variables' | 'bindings' | 'runtime-json';
