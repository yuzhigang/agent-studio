export type ScalarKind = 'string' | 'number' | 'boolean' | 'integer' | (string & {});

export interface AgentModelMetadata {
  name: string;
  title: string;
  description?: string;
  group?: string;
  creator?: string;
  createdAt?: string;
  updatedAt?: string;
  version?: string;
  tags?: string[];
}

export interface AgentFieldDefinition {
  type: ScalarKind;
  title: string;
  description?: string;
  default?: unknown;
  nullable?: boolean;
  minimum?: number;
  maximum?: number;
  enum?: string[];
  items?: Record<string, unknown>;
  schema?: Record<string, unknown>;
  ['x-unit']?: string;
  [key: string]: unknown;
}

export interface AgentModel {
  $schema: string;
  metadata: AgentModelMetadata;
  attributes: Record<string, AgentFieldDefinition>;
  variables: Record<string, AgentFieldDefinition>;
  derivedProperties?: Record<string, unknown>;
  rules?: Record<string, unknown>;
  functions?: Record<string, unknown>;
  services?: Record<string, unknown>;
  states?: Record<string, unknown>;
  transitions?: Record<string, unknown>;
  behaviors?: Record<string, unknown>;
  events?: Record<string, unknown>;
  alarms?: Record<string, unknown>;
  schedules?: Record<string, unknown>;
  goals?: Record<string, unknown>;
  decisionPolicies?: Record<string, unknown>;
  memory?: Record<string, unknown>;
  plans?: Record<string, unknown>;
}
