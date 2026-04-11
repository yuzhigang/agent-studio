export interface AgentInstanceMetadata {
  name: string;
  title: string;
  description?: string;
  creator?: string;
  createdAt?: string;
  updatedAt?: string;
  version?: string;
}

export interface AgentBinding {
  source: string;
  path?: string;
  topic?: string;
  selector?: string;
  transform?: string;
  refreshSeconds?: number;
}

export interface AgentInstance {
  $schema: string;
  id: string;
  modelId: string;
  state: string;
  metadata: AgentInstanceMetadata;
  attributes?: Record<string, unknown>;
  variables: Record<string, unknown>;
  bindings?: Record<string, AgentBinding>;
  memory?: Record<string, unknown>;
  activeGoals?: Array<Record<string, unknown>>;
  currentPlan?: Record<string, unknown>;
  extensions?: Record<string, unknown>;
}
