# Agent Studio Frontend MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a React + Ant Design 5 + Vite frontend MVP that manages agent models and model-scoped instances with structured editors for high-frequency fields, JSON editors for complex blocks, and browser-local persistence through a mock API.

**Architecture:** Create a small Vite application in the repo root and organize code as `pages + modules + shared + mocks + types`. Keep domain types separate from UI types, use direct JSON seed imports from the existing `model.json` and `ladle_001.json`, and implement persistence through a repository/service layer backed by `localStorage`. Use plain React state plus module hooks instead of a global store to keep the MVP narrow and easy to replace later.

**Tech Stack:** React, TypeScript, Vite, Ant Design 5, React Router, Vitest, React Testing Library, jsdom

---

## File Map

### Create

- `package.json`
- `tsconfig.json`
- `vite.config.ts`
- `index.html`
- `vitest.setup.ts`
- `src/main.tsx`
- `src/app/App.tsx`
- `src/app/router.tsx`
- `src/styles/globals.css`
- `src/pages/models/ModelsPage.tsx`
- `src/pages/models/ModelDetailPage.tsx`
- `src/pages/instances/InstanceDetailPage.tsx`
- `src/pages/settings/SettingsPage.tsx`
- `src/types/domain/model.ts`
- `src/types/domain/instance.ts`
- `src/types/ui/editor.ts`
- `src/shared/layout/AppLayout.tsx`
- `src/shared/components/SaveActions.tsx`
- `src/shared/components/JsonBlockEditor.tsx`
- `src/shared/hooks/useUnsavedChangesGuard.ts`
- `src/shared/lib/storage.ts`
- `src/shared/lib/json.ts`
- `src/shared/lib/validators/model.ts`
- `src/shared/lib/validators/instance.ts`
- `src/mocks/data/seedModels.ts`
- `src/mocks/data/seedInstances.ts`
- `src/mocks/repository/modelRepository.ts`
- `src/mocks/repository/instanceRepository.ts`
- `src/mocks/services/modelService.ts`
- `src/mocks/services/instanceService.ts`
- `src/modules/models/adapters/modelAdapters.ts`
- `src/modules/models/hooks/useModelsPage.ts`
- `src/modules/models/hooks/useModelDetail.ts`
- `src/modules/models/components/ModelList.tsx`
- `src/modules/models/components/CreateModelModal.tsx`
- `src/modules/models/components/ModelMetadataForm.tsx`
- `src/modules/models/components/DefinitionTableEditor.tsx`
- `src/modules/models/components/ModelEditorTabs.tsx`
- `src/modules/instances/adapters/instanceAdapters.ts`
- `src/modules/instances/hooks/useInstanceDetail.ts`
- `src/modules/instances/components/InstanceListByModel.tsx`
- `src/modules/instances/components/CreateInstanceModal.tsx`
- `src/modules/instances/components/BindingTableEditor.tsx`
- `src/modules/instances/components/RuntimeJsonPanel.tsx`
- `src/modules/instances/components/InstanceEditorTabs.tsx`

### Responsibility Notes

- `src/types/domain/*` owns the persisted shapes for models and instances.
- `src/types/ui/*` owns editor-only types such as tab keys, JSON block configs, and table rows.
- `src/mocks/data/*` imports the existing root JSON files and normalizes them as seed arrays.
- `src/mocks/repository/*` reads and writes `localStorage`.
- `src/mocks/services/*` wraps repository calls in async APIs and model-scoped instance queries.
- `src/modules/models/*` owns model list, model detail, and model editing.
- `src/modules/instances/*` owns instance list, instance detail, and instance editing.
- `src/shared/*` owns app layout, JSON editor, save bar, loading/error states, and unsaved-change guard.

## Task 1: Bootstrap the Vite App and Test Harness

**Files:**
- Create: `package.json`
- Create: `tsconfig.json`
- Create: `vite.config.ts`
- Create: `vitest.setup.ts`
- Create: `index.html`
- Create: `src/main.tsx`
- Create: `src/app/App.tsx`
- Create: `src/styles/globals.css`
- Test: `src/app/App.test.tsx`

- [ ] **Step 1: Initialize the Node workspace and install dependencies**

Run:
```bash
npm init -y
npm install react react-dom react-router-dom antd @ant-design/icons
npm install -D vite @vitejs/plugin-react typescript vitest jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event @types/react @types/react-dom @types/node
```

Expected:
- `package.json` exists at repo root
- `node_modules/` is created
- npm prints `added` lines without install errors

- [ ] **Step 2: Add the Vite, TypeScript, and Vitest config files**

Write:

`package.json`
```json
{
  "name": "agent-studio",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -p tsconfig.json && vite build",
    "test": "vitest"
  }
}
```

`tsconfig.json`
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["DOM", "DOM.Iterable", "ES2020"],
    "allowJs": false,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "forceConsistentCasingInFileNames": true,
    "module": "ESNext",
    "moduleResolution": "Node",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"]
    }
  },
  "include": ["src", "vite.config.ts", "vitest.setup.ts"]
}
```

`vite.config.ts`
```ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './vitest.setup.ts',
    globals: true,
  },
});
```

`vitest.setup.ts`
```ts
import '@testing-library/jest-dom/vitest';
```

- [ ] **Step 3: Write a failing smoke test for the app shell**

Create `src/app/App.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react';
import App from './App';

test('renders the application shell', () => {
  render(<App />);

  expect(screen.getByText('Agent Studio')).toBeInTheDocument();
  expect(screen.getByText('App shell booting')).toBeInTheDocument();
});
```

- [ ] **Step 4: Run the smoke test and verify it fails**

Run:
```bash
npm run test -- --run src/app/App.test.tsx
```

Expected: FAIL with a module-not-found or missing-component error because `src/app/App.tsx` does not exist yet.

- [ ] **Step 5: Implement the minimal app entry and styles**

Write:

`index.html`
```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Agent Studio</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`src/main.tsx`
```tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from '@/app/App';
import '@/styles/globals.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

`src/app/App.tsx`
```tsx
export default function App() {
  return (
    <main>
      <h1>Agent Studio</h1>
      <p>App shell booting</p>
    </main>
  );
}
```

`src/styles/globals.css`
```css
:root {
  font-family: "IBM Plex Sans", "PingFang SC", sans-serif;
  color: #182230;
  background:
    radial-gradient(circle at top left, rgba(181, 214, 255, 0.45), transparent 35%),
    linear-gradient(180deg, #f5f8ff 0%, #eef3f8 100%);
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-height: 100vh;
}
```

- [ ] **Step 6: Verify the scaffold passes smoke checks**

Run:
```bash
npm run test -- --run src/app/App.test.tsx
npm run build
```

Expected:
- test output contains `1 passed`
- Vite build finishes successfully and prints a generated bundle summary

- [ ] **Step 7: Commit the scaffold**

Run:
```bash
git add package.json package-lock.json tsconfig.json vite.config.ts vitest.setup.ts index.html src/main.tsx src/app/App.tsx src/app/App.test.tsx src/styles/globals.css
git commit -m "feat: bootstrap frontend app shell"
```

Expected: git creates a commit with the scaffold and smoke test.

## Task 2: Add Routing and the Shared App Layout

**Files:**
- Create: `src/app/router.tsx`
- Create: `src/shared/layout/AppLayout.tsx`
- Create: `src/pages/models/ModelsPage.tsx`
- Create: `src/pages/models/ModelDetailPage.tsx`
- Create: `src/pages/instances/InstanceDetailPage.tsx`
- Create: `src/pages/settings/SettingsPage.tsx`
- Modify: `src/app/App.tsx`
- Test: `src/app/router.test.tsx`

- [ ] **Step 1: Write a failing routing test**

Create `src/app/router.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { appRoutes } from './router';

test('redirects / to /models and renders layout navigation', async () => {
  const router = createMemoryRouter(appRoutes, {
    initialEntries: ['/'],
  });

  render(<RouterProvider router={router} />);

  expect(await screen.findByRole('link', { name: 'Models' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Settings' })).toBeInTheDocument();
  expect(await screen.findByRole('heading', { name: 'Models' })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the routing test and verify it fails**

Run:
```bash
npm run test -- --run src/app/router.test.tsx
```

Expected: FAIL because `src/app/router.tsx` and page components do not exist yet.

- [ ] **Step 3: Implement the shared layout and router definition**

Write:

`src/shared/layout/AppLayout.tsx`
```tsx
import { Layout, Menu, Typography } from 'antd';
import { Link, Outlet, useLocation } from 'react-router-dom';

const items = [
  { key: '/models', label: <Link to="/models">Models</Link> },
  { key: '/settings', label: <Link to="/settings">Settings</Link> },
];

export function AppLayout() {
  const location = useLocation();

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Layout.Sider width={220} theme="light" style={{ borderRight: '1px solid #d7e1ea' }}>
        <div style={{ padding: 20 }}>
          <Typography.Title level={4} style={{ margin: 0 }}>
            Agent Studio
          </Typography.Title>
        </div>
        <Menu mode="inline" selectedKeys={[location.pathname.startsWith('/settings') ? '/settings' : '/models']} items={items} />
      </Layout.Sider>
      <Layout>
        <Layout.Content style={{ padding: 24 }}>
          <Outlet />
        </Layout.Content>
      </Layout>
    </Layout>
  );
}
```

`src/app/router.tsx`
```tsx
import { Navigate, RouteObject } from 'react-router-dom';
import { AppLayout } from '@/shared/layout/AppLayout';
import { ModelsPage } from '@/pages/models/ModelsPage';
import { ModelDetailPage } from '@/pages/models/ModelDetailPage';
import { InstanceDetailPage } from '@/pages/instances/InstanceDetailPage';
import { SettingsPage } from '@/pages/settings/SettingsPage';

export const appRoutes: RouteObject[] = [
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to="/models" replace /> },
      { path: 'models', element: <ModelsPage /> },
      { path: 'models/:modelId', element: <ModelDetailPage /> },
      { path: 'models/:modelId/instances/:instanceId', element: <InstanceDetailPage /> },
      { path: 'settings', element: <SettingsPage /> },
    ],
  },
];
```

- [ ] **Step 4: Add the route pages and mount the router**

Write:

`src/pages/models/ModelsPage.tsx`
```tsx
export function ModelsPage() {
  return <h2>Models</h2>;
}
```

`src/pages/models/ModelDetailPage.tsx`
```tsx
export function ModelDetailPage() {
  return <h2>Model Detail</h2>;
}
```

`src/pages/instances/InstanceDetailPage.tsx`
```tsx
export function InstanceDetailPage() {
  return <h2>Instance Detail</h2>;
}
```

`src/pages/settings/SettingsPage.tsx`
```tsx
export function SettingsPage() {
  return <h2>Settings</h2>;
}
```

`src/app/App.tsx`
```tsx
import { RouterProvider, createBrowserRouter } from 'react-router-dom';
import { appRoutes } from './router';

const router = createBrowserRouter(appRoutes);

export default function App() {
  return <RouterProvider router={router} />;
}
```

- [ ] **Step 5: Verify layout and routing**

Run:
```bash
npm run test -- --run src/app/router.test.tsx
npm run build
```

Expected:
- routing test passes
- build completes successfully

- [ ] **Step 6: Commit the routing layer**

Run:
```bash
git add src/app/App.tsx src/app/router.tsx src/app/router.test.tsx src/shared/layout/AppLayout.tsx src/pages/models/ModelsPage.tsx src/pages/models/ModelDetailPage.tsx src/pages/instances/InstanceDetailPage.tsx src/pages/settings/SettingsPage.tsx
git commit -m "feat: add routed application shell"
```

Expected: git creates a commit for layout and routes.

## Task 3: Define Domain Types, UI Types, Seed Imports, and Validators

**Files:**
- Create: `src/types/domain/model.ts`
- Create: `src/types/domain/instance.ts`
- Create: `src/types/ui/editor.ts`
- Create: `src/shared/lib/validators/model.ts`
- Create: `src/shared/lib/validators/instance.ts`
- Create: `src/shared/lib/json.ts`
- Create: `src/mocks/data/seedModels.ts`
- Create: `src/mocks/data/seedInstances.ts`
- Create: `src/modules/models/adapters/modelAdapters.ts`
- Create: `src/modules/instances/adapters/instanceAdapters.ts`
- Test: `src/modules/models/adapters/modelAdapters.test.ts`
- Test: `src/modules/instances/adapters/instanceAdapters.test.ts`

- [ ] **Step 1: Write failing adapter and validator tests**

Create `src/modules/models/adapters/modelAdapters.test.ts`:
```ts
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
```

Create `src/modules/instances/adapters/instanceAdapters.test.ts`:
```ts
import { seedInstances } from '@/mocks/data/seedInstances';
import { buildBindingRows, buildRuntimeJsonBlocks } from './instanceAdapters';
import { validateInstanceDraft } from '@/shared/lib/validators/instance';

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
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:
```bash
npm run test -- --run src/modules/models/adapters/modelAdapters.test.ts src/modules/instances/adapters/instanceAdapters.test.ts
```

Expected: FAIL because the seed, type, validator, and adapter modules do not exist yet.

- [ ] **Step 3: Implement domain types, UI types, and seed imports**

Write:

`src/types/domain/model.ts`
```ts
export type ScalarKind = 'string' | 'number' | 'boolean' | 'integer';

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
  ['x-unit']?: string;
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
```

`src/types/domain/instance.ts`
```ts
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
  attributes: Record<string, unknown>;
  variables: Record<string, unknown>;
  bindings: Record<string, AgentBinding>;
  memory?: Record<string, unknown>;
  activeGoals?: Array<Record<string, unknown>>;
  currentPlan?: Record<string, unknown>;
  extensions?: Record<string, unknown>;
}
```

`src/types/ui/editor.ts`
```ts
export interface DefinitionTableRow {
  key: string;
  title: string;
  type: string;
  description?: string;
  defaultValue?: unknown;
  nullable?: boolean;
}

export interface JsonBlockConfig {
  key: string;
  label: string;
  value: unknown;
}

export type ModelEditorTabKey = 'basic' | 'attributes' | 'variables' | 'advanced-json';
export type InstanceEditorTabKey = 'basic' | 'attributes' | 'variables' | 'bindings' | 'runtime-json';
```

`src/mocks/data/seedModels.ts`
```ts
import rawModel from '../../../model.json';
import type { AgentModel } from '@/types/domain/model';

export const seedModels: AgentModel[] = [rawModel as AgentModel];
```

`src/mocks/data/seedInstances.ts`
```ts
import rawInstance from '../../../ladle_001.json';
import type { AgentInstance } from '@/types/domain/instance';

export const seedInstances: AgentInstance[] = [rawInstance as AgentInstance];
```

- [ ] **Step 4: Implement validators, JSON helpers, and adapters**

Write:

`src/shared/lib/json.ts`
```ts
export const prettyJson = (value: unknown) => JSON.stringify(value ?? {}, null, 2);

export function parseJsonBlock<T>(input: string): T {
  return JSON.parse(input) as T;
}
```

`src/shared/lib/validators/model.ts`
```ts
import type { AgentModel } from '@/types/domain/model';

export function validateModelDraft(model: AgentModel): string[] {
  const errors: string[] = [];

  if (!model.metadata.name?.trim()) errors.push('metadata.name is required');
  if (!model.metadata.title?.trim()) errors.push('metadata.title is required');

  for (const [name, definition] of Object.entries(model.attributes ?? {})) {
    if (!definition.title?.trim()) errors.push(`attributes.${name}.title is required`);
    if (definition.minimum !== undefined && definition.maximum !== undefined && definition.minimum > definition.maximum) {
      errors.push(`attributes.${name}.minimum must be less than or equal to maximum`);
    }
  }

  for (const [name, definition] of Object.entries(model.variables ?? {})) {
    if (!definition.title?.trim()) errors.push(`variables.${name}.title is required`);
    if (definition.minimum !== undefined && definition.maximum !== undefined && definition.minimum > definition.maximum) {
      errors.push(`variables.${name}.minimum must be less than or equal to maximum`);
    }
  }

  return errors;
}
```

`src/shared/lib/validators/instance.ts`
```ts
import type { AgentInstance } from '@/types/domain/instance';

export function validateInstanceDraft(instance: AgentInstance): string[] {
  const errors: string[] = [];

  if (!instance.id.trim()) errors.push('id is required');
  if (!instance.modelId.trim()) errors.push('modelId is required');
  if (!instance.state.trim()) errors.push('state is required');
  if (!instance.metadata.name?.trim()) errors.push('metadata.name is required');
  if (!instance.metadata.title?.trim()) errors.push('metadata.title is required');

  return errors;
}
```

`src/modules/models/adapters/modelAdapters.ts`
```ts
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
```

`src/modules/instances/adapters/instanceAdapters.ts`
```ts
import type { AgentBinding, AgentInstance } from '@/types/domain/instance';
import type { JsonBlockConfig } from '@/types/ui/editor';

export function buildBindingRows(bindings: Record<string, AgentBinding>) {
  return Object.entries(bindings).map(([name, binding]) => ({
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
```

- [ ] **Step 5: Verify adapters and validators**

Run:
```bash
npm run test -- --run src/modules/models/adapters/modelAdapters.test.ts src/modules/instances/adapters/instanceAdapters.test.ts
```

Expected: both test files pass.

- [ ] **Step 6: Commit the type and seed layer**

Run:
```bash
git add src/types/domain src/types/ui src/shared/lib/json.ts src/shared/lib/validators src/mocks/data src/modules/models/adapters src/modules/instances/adapters
git commit -m "feat: add domain types and seed adapters"
```

Expected: git records the type, seed, validator, and adapter layer.

## Task 4: Implement Local Persistence and Mock Services

**Files:**
- Create: `src/shared/lib/storage.ts`
- Create: `src/mocks/repository/modelRepository.ts`
- Create: `src/mocks/repository/instanceRepository.ts`
- Create: `src/mocks/services/modelService.ts`
- Create: `src/mocks/services/instanceService.ts`
- Test: `src/mocks/services/modelService.test.ts`
- Test: `src/mocks/services/instanceService.test.ts`

- [ ] **Step 1: Write failing service tests**

Create `src/mocks/services/modelService.test.ts`:
```ts
import { beforeEach, expect, test } from 'vitest';
import { modelService } from './modelService';

beforeEach(() => {
  localStorage.clear();
});

test('loads seed models on first read', async () => {
  const models = await modelService.list();
  expect(models[0].metadata.name).toBe('ladle');
});

test('creates and persists a model', async () => {
  await modelService.create({
    ...structuredClone((await modelService.list())[0]),
    metadata: {
      ...structuredClone((await modelService.list())[0]).metadata,
      name: 'crane',
      title: 'Crane',
    },
  });

  const models = await modelService.list();
  expect(models.some((model) => model.metadata.name === 'crane')).toBe(true);
});
```

Create `src/mocks/services/instanceService.test.ts`:
```ts
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
```

- [ ] **Step 2: Run the service tests and verify they fail**

Run:
```bash
npm run test -- --run src/mocks/services/modelService.test.ts src/mocks/services/instanceService.test.ts
```

Expected: FAIL because the storage, repository, and service modules do not exist yet.

- [ ] **Step 3: Implement the storage and repository layers**

Write:

`src/shared/lib/storage.ts`
```ts
export function readStorage<T>(key: string, fallback: T): T {
  const raw = localStorage.getItem(key);
  return raw ? (JSON.parse(raw) as T) : fallback;
}

export function writeStorage<T>(key: string, value: T) {
  localStorage.setItem(key, JSON.stringify(value));
}

export function removeStorage(key: string) {
  localStorage.removeItem(key);
}
```

`src/mocks/repository/modelRepository.ts`
```ts
import { seedModels } from '@/mocks/data/seedModels';
import type { AgentModel } from '@/types/domain/model';
import { readStorage, writeStorage } from '@/shared/lib/storage';

const MODELS_KEY = 'agent-studio/models/v1';

function loadAll(): AgentModel[] {
  const models = readStorage<AgentModel[]>(MODELS_KEY, []);
  if (models.length > 0) return models;
  writeStorage(MODELS_KEY, seedModels);
  return seedModels;
}

export const modelRepository = {
  list: () => loadAll(),
  getByName: (modelId: string) => loadAll().find((model) => model.metadata.name === modelId) ?? null,
  saveAll: (models: AgentModel[]) => writeStorage(MODELS_KEY, models),
  reset: () => writeStorage(MODELS_KEY, seedModels),
};
```

`src/mocks/repository/instanceRepository.ts`
```ts
import { seedInstances } from '@/mocks/data/seedInstances';
import type { AgentInstance } from '@/types/domain/instance';
import { readStorage, writeStorage } from '@/shared/lib/storage';

const INSTANCES_KEY = 'agent-studio/instances/v1';

function loadAll(): AgentInstance[] {
  const instances = readStorage<AgentInstance[]>(INSTANCES_KEY, []);
  if (instances.length > 0) return instances;
  writeStorage(INSTANCES_KEY, seedInstances);
  return seedInstances;
}

export const instanceRepository = {
  list: () => loadAll(),
  getById: (instanceId: string) => loadAll().find((instance) => instance.id === instanceId) ?? null,
  listByModel: (modelId: string) => loadAll().filter((instance) => instance.modelId === modelId),
  saveAll: (instances: AgentInstance[]) => writeStorage(INSTANCES_KEY, instances),
  reset: () => writeStorage(INSTANCES_KEY, seedInstances),
};
```

- [ ] **Step 4: Implement async mock services**

Write:

`src/mocks/services/modelService.ts`
```ts
import { modelRepository } from '@/mocks/repository/modelRepository';
import type { AgentModel } from '@/types/domain/model';

const delay = (ms = 80) => new Promise((resolve) => setTimeout(resolve, ms));

export const modelService = {
  async list() {
    await delay();
    return modelRepository.list();
  },
  async getByName(modelId: string) {
    await delay();
    return modelRepository.getByName(modelId);
  },
  async create(model: AgentModel) {
    await delay();
    const next = [...modelRepository.list(), model];
    modelRepository.saveAll(next);
    return model;
  },
  async update(model: AgentModel) {
    await delay();
    const next = modelRepository.list().map((item) => (item.metadata.name === model.metadata.name ? model : item));
    modelRepository.saveAll(next);
    return model;
  },
  async reset() {
    await delay();
    modelRepository.reset();
  },
};
```

`src/mocks/services/instanceService.ts`
```ts
import { instanceRepository } from '@/mocks/repository/instanceRepository';
import type { AgentInstance } from '@/types/domain/instance';

const delay = (ms = 80) => new Promise((resolve) => setTimeout(resolve, ms));

export const instanceService = {
  async listByModel(modelId: string) {
    await delay();
    return instanceRepository.listByModel(modelId);
  },
  async getById(instanceId: string) {
    await delay();
    return instanceRepository.getById(instanceId);
  },
  async create(instance: AgentInstance) {
    await delay();
    const next = [...instanceRepository.list(), instance];
    instanceRepository.saveAll(next);
    return instance;
  },
  async update(instance: AgentInstance) {
    await delay();
    const next = instanceRepository.list().map((item) => (item.id === instance.id ? instance : item));
    instanceRepository.saveAll(next);
    return instance;
  },
  async reset() {
    await delay();
    instanceRepository.reset();
  },
};
```

- [ ] **Step 5: Verify persistence and seed behavior**

Run:
```bash
npm run test -- --run src/mocks/services/modelService.test.ts src/mocks/services/instanceService.test.ts
```

Expected: both service test files pass and prove seed hydration plus local persistence.

- [ ] **Step 6: Commit the mock data layer**

Run:
```bash
git add src/shared/lib/storage.ts src/mocks/repository src/mocks/services
git commit -m "feat: add mock persistence services"
```

Expected: git creates a commit for storage, repositories, and services.

## Task 5: Build Model List, Model Detail, and Model Editors

**Files:**
- Create: `src/shared/components/SaveActions.tsx`
- Create: `src/shared/components/JsonBlockEditor.tsx`
- Create: `src/modules/models/hooks/useModelsPage.ts`
- Create: `src/modules/models/hooks/useModelDetail.ts`
- Create: `src/modules/models/components/ModelList.tsx`
- Create: `src/modules/models/components/CreateModelModal.tsx`
- Create: `src/modules/models/components/ModelMetadataForm.tsx`
- Create: `src/modules/models/components/DefinitionTableEditor.tsx`
- Create: `src/modules/models/components/ModelEditorTabs.tsx`
- Modify: `src/pages/models/ModelsPage.tsx`
- Modify: `src/pages/models/ModelDetailPage.tsx`
- Test: `src/pages/models/ModelsPage.test.tsx`
- Test: `src/pages/models/ModelDetailPage.test.tsx`

- [ ] **Step 1: Write a failing models page test**

Create `src/pages/models/ModelsPage.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { ModelsPage } from './ModelsPage';

test('renders models and creates a new model', async () => {
  const user = userEvent.setup();

  render(
    <MemoryRouter>
      <ModelsPage />
    </MemoryRouter>,
  );

  expect(await screen.findByText('钢包智能体')).toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: 'New Model' }));
  await user.type(screen.getByLabelText('Name'), 'scheduler');
  await user.type(screen.getByLabelText('Title'), '调度智能体');
  await user.click(screen.getByRole('button', { name: 'Create' }));

  expect(await screen.findByText('调度智能体')).toBeInTheDocument();
});
```

- [ ] **Step 2: Implement the models page and list flow**

Write:

`src/modules/models/hooks/useModelsPage.ts`
```ts
import { useEffect, useState } from 'react';
import { modelService } from '@/mocks/services/modelService';
import type { AgentModel } from '@/types/domain/model';

export function useModelsPage() {
  const [models, setModels] = useState<AgentModel[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    modelService.list().then((next) => {
      setModels(next);
      setLoading(false);
    });
  }, []);

  async function createModel(model: AgentModel) {
    const saved = await modelService.create(model);
    setModels((current) => [...current, saved]);
  }

  return { models, loading, createModel };
}
```

`src/modules/models/components/ModelList.tsx`
```tsx
import { List } from 'antd';
import { Link } from 'react-router-dom';
import type { AgentModel } from '@/types/domain/model';

interface Props {
  models: AgentModel[];
}

export function ModelList({ models }: Props) {
  return (
    <List
      dataSource={models}
      renderItem={(model) => (
        <List.Item>
          <List.Item.Meta
            title={<Link to={`/models/${model.metadata.name}`}>{model.metadata.title}</Link>}
            description={model.metadata.description}
          />
        </List.Item>
      )}
    />
  );
}
```

`src/modules/models/components/CreateModelModal.tsx`
```tsx
import { Button, Form, Input, Modal } from 'antd';
import { useState } from 'react';
import type { AgentModel } from '@/types/domain/model';

interface Props {
  onCreate: (model: AgentModel) => Promise<void> | void;
}

export function CreateModelModal({ onCreate }: Props) {
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm<{ name: string; title: string }>();

  return (
    <>
      <Button type="primary" onClick={() => setOpen(true)}>
        New Model
      </Button>
      <Modal
        open={open}
        title="Create Model"
        onCancel={() => setOpen(false)}
        footer={null}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={async (values) => {
            await onCreate({
              $schema: 'https://agent-studio.io/schema/v2',
              metadata: { name: values.name, title: values.title },
              attributes: {},
              variables: {},
            });
            setOpen(false);
            form.resetFields();
          }}
        >
          <Form.Item name="name" label="Name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="title" label="Title" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Button htmlType="submit" type="primary">
            Create
          </Button>
        </Form>
      </Modal>
    </>
  );
}
```

`src/pages/models/ModelsPage.tsx`
```tsx
import { Card, Flex, Spin, Typography } from 'antd';
import { CreateModelModal } from '@/modules/models/components/CreateModelModal';
import { ModelList } from '@/modules/models/components/ModelList';
import { useModelsPage } from '@/modules/models/hooks/useModelsPage';

export function ModelsPage() {
  const { models, loading, createModel } = useModelsPage();

  return (
    <Card>
      <Flex justify="space-between" align="center" style={{ marginBottom: 16 }}>
        <Typography.Title level={2} style={{ margin: 0 }}>
          Models
        </Typography.Title>
        <CreateModelModal onCreate={createModel} />
      </Flex>
      {loading ? <Spin /> : <ModelList models={models} />}
    </Card>
  );
}
```

- [ ] **Step 3: Write a failing model detail editor test**

Create `src/pages/models/ModelDetailPage.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ModelDetailPage } from './ModelDetailPage';

test('edits model metadata and saves the update', async () => {
  const user = userEvent.setup();

  render(
    <MemoryRouter initialEntries={['/models/ladle']}>
      <Routes>
        <Route path="/models/:modelId" element={<ModelDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );

  expect(await screen.findByDisplayValue('钢包智能体')).toBeInTheDocument();

  await user.clear(screen.getByLabelText('Title'));
  await user.type(screen.getByLabelText('Title'), '钢包智能体 MVP');
  await user.click(screen.getByRole('button', { name: 'Save' }));

  expect(await screen.findByText('Saved')).toBeInTheDocument();
});
```

- [ ] **Step 4: Implement the shared editors and model detail page**

Write:

`src/shared/components/SaveActions.tsx`
```tsx
import { Button, Flex, Tag } from 'antd';

interface Props {
  dirty: boolean;
  saving?: boolean;
  onSave: () => void;
  onReset: () => void;
}

export function SaveActions({ dirty, saving, onSave, onReset }: Props) {
  return (
    <Flex gap={12} align="center">
      <Tag color={dirty ? 'gold' : 'green'}>{dirty ? 'Unsaved changes' : 'Saved'}</Tag>
      <Button onClick={onReset} disabled={!dirty}>
        Reset
      </Button>
      <Button type="primary" onClick={onSave} loading={saving}>
        Save
      </Button>
    </Flex>
  );
}
```

`src/shared/components/JsonBlockEditor.tsx`
```tsx
import { Alert, Input } from 'antd';

interface Props {
  label: string;
  value: string;
  error?: string | null;
  onChange: (value: string) => void;
}

export function JsonBlockEditor({ label, value, error, onChange }: Props) {
  return (
    <>
      {error ? <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} /> : null}
      <Input.TextArea
        aria-label={label}
        autoSize={{ minRows: 14 }}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </>
  );
}
```

`src/modules/models/hooks/useModelDetail.ts`
```ts
import { message } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { modelService } from '@/mocks/services/modelService';
import { prettyJson, parseJsonBlock } from '@/shared/lib/json';
import { validateModelDraft } from '@/shared/lib/validators/model';
import type { AgentModel } from '@/types/domain/model';

export function useModelDetail(modelId: string) {
  const [original, setOriginal] = useState<AgentModel | null>(null);
  const [draft, setDraft] = useState<AgentModel | null>(null);
  const [saving, setSaving] = useState(false);
  const [jsonErrors, setJsonErrors] = useState<Record<string, string | null>>({});

  useEffect(() => {
    modelService.getByName(modelId).then((model) => {
      setOriginal(model);
      setDraft(model ? structuredClone(model) : null);
    });
  }, [modelId]);

  const dirty = useMemo(() => JSON.stringify(original) !== JSON.stringify(draft), [original, draft]);

  async function save() {
    if (!draft) return;
    const errors = validateModelDraft(draft);
    if (errors.length > 0) {
      message.error(errors[0]);
      return;
    }
    setSaving(true);
    await modelService.update(draft);
    setOriginal(structuredClone(draft));
    setSaving(false);
    message.success('Saved');
  }

  function reset() {
    setDraft(original ? structuredClone(original) : null);
  }

  function setMetadata<K extends keyof AgentModel['metadata']>(key: K, value: AgentModel['metadata'][K]) {
    setDraft((current) => current ? { ...current, metadata: { ...current.metadata, [key]: value } } : current);
  }

  function setDefinitions(section: 'attributes' | 'variables', value: AgentModel['attributes'] | AgentModel['variables']) {
    setDraft((current) => current ? { ...current, [section]: value } : current);
  }

  function updateJsonBlock(key: keyof AgentModel, raw: string) {
    try {
      const parsed = parseJsonBlock<unknown>(raw);
      setJsonErrors((current) => ({ ...current, [key]: null }));
      setDraft((current) => current ? { ...current, [key]: parsed } : current);
    } catch (error) {
      setJsonErrors((current) => ({ ...current, [key]: (error as Error).message }));
    }
  }

  return {
    original,
    draft,
    dirty,
    saving,
    jsonErrors,
    save,
    reset,
    setMetadata,
    setDefinitions,
    updateJsonBlock,
    prettyJson,
  };
}
```

`src/modules/models/components/ModelMetadataForm.tsx`
```tsx
import { Form, Input } from 'antd';
import type { AgentModelMetadata } from '@/types/domain/model';

interface Props {
  value: AgentModelMetadata;
  onChange: <K extends keyof AgentModelMetadata>(key: K, value: AgentModelMetadata[K]) => void;
}

export function ModelMetadataForm({ value, onChange }: Props) {
  return (
    <Form layout="vertical">
      <Form.Item label="Name">
        <Input value={value.name} onChange={(event) => onChange('name', event.target.value)} />
      </Form.Item>
      <Form.Item label="Title">
        <Input value={value.title} onChange={(event) => onChange('title', event.target.value)} />
      </Form.Item>
      <Form.Item label="Description">
        <Input.TextArea value={value.description} onChange={(event) => onChange('description', event.target.value)} />
      </Form.Item>
    </Form>
  );
}
```

`src/modules/models/components/DefinitionTableEditor.tsx`
```tsx
import { Button, Form, Input, InputNumber, Modal, Space, Switch, Table } from 'antd';
import { useMemo, useState } from 'react';
import type { AgentFieldDefinition } from '@/types/domain/model';
import { buildDefinitionRows } from '@/modules/models/adapters/modelAdapters';

interface Props {
  label: string;
  value: Record<string, AgentFieldDefinition>;
  onChange: (value: Record<string, AgentFieldDefinition>) => void;
}

export function DefinitionTableEditor({ label, value, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [form] = Form.useForm();
  const rows = useMemo(() => buildDefinitionRows(value), [value]);

  function openEditor(key?: string) {
    const nextKey = key ?? '';
    setEditingKey(key ?? null);
    form.setFieldsValue(key ? { name: key, ...value[key] } : { name: '', type: 'string', nullable: false });
    setOpen(true);
  }

  async function submit() {
    const next = await form.validateFields();
    const { name, ...rest } = next;
    onChange({ ...value, [name]: rest });
    setOpen(false);
    setEditingKey(null);
  }

  return (
    <>
      <Space style={{ marginBottom: 12 }}>
        <strong>{label}</strong>
        <Button onClick={() => openEditor()}>Add</Button>
      </Space>
      <Table
        rowKey="key"
        pagination={false}
        dataSource={rows}
        columns={[
          { title: 'Name', dataIndex: 'key' },
          { title: 'Title', dataIndex: 'title' },
          { title: 'Type', dataIndex: 'type' },
          { title: 'Nullable', dataIndex: 'nullable', render: (value) => (value ? 'Yes' : 'No') },
          {
            title: 'Action',
            render: (_, row) => <Button onClick={() => openEditor(row.key)}>Edit</Button>,
          },
        ]}
      />
      <Modal open={open} title={editingKey ? 'Edit Definition' : 'Add Definition'} onCancel={() => setOpen(false)} onOk={submit}>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="Name" rules={[{ required: true }]}>
            <Input disabled={!!editingKey} />
          </Form.Item>
          <Form.Item name="title" label="Title" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="type" label="Type" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <Input.TextArea />
          </Form.Item>
          <Form.Item name="minimum" label="Minimum">
            <InputNumber style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="maximum" label="Maximum">
            <InputNumber style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="nullable" label="Nullable" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
```

`src/modules/models/components/ModelEditorTabs.tsx`
```tsx
import { Tabs } from 'antd';
import { buildModelJsonBlocks } from '@/modules/models/adapters/modelAdapters';
import { DefinitionTableEditor } from './DefinitionTableEditor';
import { JsonBlockEditor } from '@/shared/components/JsonBlockEditor';
import { ModelMetadataForm } from './ModelMetadataForm';
import type { AgentModel } from '@/types/domain/model';

interface Props {
  model: AgentModel;
  jsonErrors: Record<string, string | null>;
  prettyJson: (value: unknown) => string;
  onMetadataChange: <K extends keyof AgentModel['metadata']>(key: K, value: AgentModel['metadata'][K]) => void;
  onAttributesChange: (value: AgentModel['attributes']) => void;
  onVariablesChange: (value: AgentModel['variables']) => void;
  onJsonChange: (key: keyof AgentModel, value: string) => void;
}

export function ModelEditorTabs(props: Props) {
  const jsonBlocks = buildModelJsonBlocks(props.model);

  return (
    <Tabs
      items={[
        {
          key: 'basic',
          label: 'Basic',
          children: <ModelMetadataForm value={props.model.metadata} onChange={props.onMetadataChange} />,
        },
        {
          key: 'attributes',
          label: 'Attributes',
          children: <DefinitionTableEditor label="Attributes" value={props.model.attributes} onChange={props.onAttributesChange} />,
        },
        {
          key: 'variables',
          label: 'Variables',
          children: <DefinitionTableEditor label="Variables" value={props.model.variables} onChange={props.onVariablesChange} />,
        },
        {
          key: 'advanced-json',
          label: 'Advanced JSON',
          children: jsonBlocks.map((block) => (
            <div key={block.key} style={{ marginBottom: 16 }}>
              <h4>{block.label}</h4>
              <JsonBlockEditor
                label={block.label}
                value={props.prettyJson(block.value)}
                error={props.jsonErrors[block.key] ?? null}
                onChange={(value) => props.onJsonChange(block.key as keyof AgentModel, value)}
              />
            </div>
          )),
        },
      ]}
    />
  );
}
```

`src/pages/models/ModelDetailPage.tsx`
```tsx
import { Alert, Card, Spin } from 'antd';
import { useParams } from 'react-router-dom';
import { ModelEditorTabs } from '@/modules/models/components/ModelEditorTabs';
import { useModelDetail } from '@/modules/models/hooks/useModelDetail';
import { SaveActions } from '@/shared/components/SaveActions';

export function ModelDetailPage() {
  const { modelId = '' } = useParams();
  const { draft, dirty, saving, jsonErrors, save, reset, setMetadata, setDefinitions, updateJsonBlock, prettyJson } = useModelDetail(modelId);

  if (!draft) return <Spin />;

  return (
    <Card title={draft.metadata.title} extra={<SaveActions dirty={dirty} saving={saving} onSave={save} onReset={reset} />}>
      {Object.values(jsonErrors).some(Boolean) ? <Alert type="warning" message="Fix JSON errors before saving." style={{ marginBottom: 16 }} /> : null}
      <ModelEditorTabs
        model={draft}
        jsonErrors={jsonErrors}
        prettyJson={prettyJson}
        onMetadataChange={setMetadata}
        onAttributesChange={(value) => setDefinitions('attributes', value)}
        onVariablesChange={(value) => setDefinitions('variables', value)}
        onJsonChange={updateJsonBlock}
      />
    </Card>
  );
}
```

- [ ] **Step 5: Verify model list and model detail flows**

Run:
```bash
npm run test -- --run src/pages/models/ModelsPage.test.tsx src/pages/models/ModelDetailPage.test.tsx
npm run build
```

Expected:
- the model list test passes
- the model detail save test passes
- the application still builds successfully

- [ ] **Step 6: Commit the model management UI**

Run:
```bash
git add src/shared/components/SaveActions.tsx src/shared/components/JsonBlockEditor.tsx src/modules/models src/pages/models
git commit -m "feat: add model management workspace"
```

Expected: git creates a commit for models list, detail, and editors.

## Task 6: Build Model-Scoped Instance List and Instance Editors

**Files:**
- Create: `src/modules/instances/hooks/useInstanceDetail.ts`
- Create: `src/modules/instances/components/InstanceListByModel.tsx`
- Create: `src/modules/instances/components/CreateInstanceModal.tsx`
- Create: `src/modules/instances/components/BindingTableEditor.tsx`
- Create: `src/modules/instances/components/RuntimeJsonPanel.tsx`
- Create: `src/modules/instances/components/InstanceEditorTabs.tsx`
- Modify: `src/pages/models/ModelDetailPage.tsx`
- Modify: `src/pages/instances/InstanceDetailPage.tsx`
- Test: `src/pages/models/ModelDetailPage.instances.test.tsx`
- Test: `src/pages/instances/InstanceDetailPage.test.tsx`

- [ ] **Step 1: Write a failing model-detail instance-list test**

Create `src/pages/models/ModelDetailPage.instances.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ModelDetailPage } from './ModelDetailPage';

test('shows instances for the current model and creates a new instance', async () => {
  const user = userEvent.setup();

  render(
    <MemoryRouter initialEntries={['/models/ladle']}>
      <Routes>
        <Route path="/models/:modelId" element={<ModelDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );

  expect(await screen.findByText('1号钢包')).toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: 'New Instance' }));
  await user.type(screen.getByLabelText('Instance ID'), 'ladle_002');
  await user.type(screen.getByLabelText('Title'), '2号钢包');
  await user.click(screen.getByRole('button', { name: 'Create' }));

  expect(await screen.findByText('2号钢包')).toBeInTheDocument();
});
```

- [ ] **Step 2: Implement the model-scoped instance list and creation flow**

Write:

`src/modules/instances/components/InstanceListByModel.tsx`
```tsx
import { List } from 'antd';
import { Link } from 'react-router-dom';
import type { AgentInstance } from '@/types/domain/instance';

interface Props {
  modelId: string;
  instances: AgentInstance[];
}

export function InstanceListByModel({ modelId, instances }: Props) {
  return (
    <List
      header="Instances"
      dataSource={instances}
      renderItem={(instance) => (
        <List.Item>
          <List.Item.Meta
            title={<Link to={`/models/${modelId}/instances/${instance.id}`}>{instance.metadata.title}</Link>}
            description={instance.metadata.description}
          />
        </List.Item>
      )}
    />
  );
}
```

`src/modules/instances/components/CreateInstanceModal.tsx`
```tsx
import { Button, Form, Input, Modal, Select } from 'antd';
import { useState } from 'react';
import type { AgentInstance } from '@/types/domain/instance';
import type { AgentModel } from '@/types/domain/model';

interface Props {
  model: AgentModel;
  onCreate: (instance: AgentInstance) => Promise<void> | void;
}

export function CreateInstanceModal({ model, onCreate }: Props) {
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm<{ id: string; title: string; state: string }>();
  const stateOptions = Object.keys(model.states ?? {});

  return (
    <>
      <Button onClick={() => setOpen(true)}>New Instance</Button>
      <Modal open={open} title="Create Instance" footer={null} onCancel={() => setOpen(false)}>
        <Form
          form={form}
          layout="vertical"
          initialValues={{ state: stateOptions[0] ?? 'initialized' }}
          onFinish={async (values) => {
            await onCreate({
              $schema: 'https://agent-studio.io/schema/v2/instance',
              id: values.id,
              modelId: model.metadata.name,
              state: values.state,
              metadata: { name: values.id, title: values.title },
              attributes: Object.fromEntries(Object.entries(model.attributes).map(([key, value]) => [key, value.default ?? null])),
              variables: Object.fromEntries(Object.entries(model.variables).map(([key, value]) => [key, value.default ?? null])),
              bindings: {},
              memory: {},
              activeGoals: [],
              currentPlan: {},
              extensions: {},
            });
            setOpen(false);
            form.resetFields();
          }}
        >
          <Form.Item name="id" label="Instance ID" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="title" label="Title" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="state" label="State" rules={[{ required: true }]}>
            <Select options={(stateOptions.length > 0 ? stateOptions : ['initialized']).map((value) => ({ label: value, value }))} />
          </Form.Item>
          <Button htmlType="submit" type="primary">
            Create
          </Button>
        </Form>
      </Modal>
    </>
  );
}
```

Modify `src/pages/models/ModelDetailPage.tsx` so it loads instances for the current model and renders both the instance list and `CreateInstanceModal` below the model editor card.

Updated `src/pages/models/ModelDetailPage.tsx` shape:
```tsx
import { Alert, Card, Flex, Spin } from 'antd';
import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { instanceService } from '@/mocks/services/instanceService';
import { CreateInstanceModal } from '@/modules/instances/components/CreateInstanceModal';
import { InstanceListByModel } from '@/modules/instances/components/InstanceListByModel';
import type { AgentInstance } from '@/types/domain/instance';
import { ModelEditorTabs } from '@/modules/models/components/ModelEditorTabs';
import { useModelDetail } from '@/modules/models/hooks/useModelDetail';
import { SaveActions } from '@/shared/components/SaveActions';

export function ModelDetailPage() {
  const { modelId = '' } = useParams();
  const { draft, dirty, saving, jsonErrors, save, reset, setMetadata, setDefinitions, updateJsonBlock, prettyJson } = useModelDetail(modelId);
  const [instances, setInstances] = useState<AgentInstance[]>([]);

  useEffect(() => {
    instanceService.listByModel(modelId).then(setInstances);
  }, [modelId]);

  if (!draft) return <Spin />;

  return (
    <Flex vertical gap={16}>
      <Card title={draft.metadata.title} extra={<SaveActions dirty={dirty} saving={saving} onSave={save} onReset={reset} />}>
        {Object.values(jsonErrors).some(Boolean) ? <Alert type="warning" message="Fix JSON errors before saving." style={{ marginBottom: 16 }} /> : null}
        <ModelEditorTabs
          model={draft}
          jsonErrors={jsonErrors}
          prettyJson={prettyJson}
          onMetadataChange={setMetadata}
          onAttributesChange={(value) => setDefinitions('attributes', value)}
          onVariablesChange={(value) => setDefinitions('variables', value)}
          onJsonChange={updateJsonBlock}
        />
      </Card>
      <Card
        title="Instances"
        extra={
          <CreateInstanceModal
            model={draft}
            onCreate={async (instance) => {
              const saved = await instanceService.create(instance);
              setInstances((current) => [...current, saved]);
            }}
          />
        }
      >
        <InstanceListByModel modelId={draft.metadata.name} instances={instances} />
      </Card>
    </Flex>
  );
}
```

- [ ] **Step 3: Write a failing instance detail editor test**

Create `src/pages/instances/InstanceDetailPage.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { InstanceDetailPage } from './InstanceDetailPage';

test('edits instance variables and bindings and saves them', async () => {
  const user = userEvent.setup();

  render(
    <MemoryRouter initialEntries={['/models/ladle/instances/ladle_001']}>
      <Routes>
        <Route path="/models/:modelId/instances/:instanceId" element={<InstanceDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );

  expect(await screen.findByDisplayValue('1号钢包')).toBeInTheDocument();

  await user.click(screen.getByRole('tab', { name: 'Variables' }));
  await user.clear(screen.getByLabelText('processStatus'));
  await user.type(screen.getByLabelText('processStatus'), 'transport_ready');
  await user.click(screen.getByRole('button', { name: 'Save' }));

  expect(await screen.findByText('Saved')).toBeInTheDocument();
});
```

- [ ] **Step 4: Implement the instance detail hook and editor tabs**

Write:

`src/modules/instances/hooks/useInstanceDetail.ts`
```ts
import { message } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { instanceService } from '@/mocks/services/instanceService';
import { prettyJson, parseJsonBlock } from '@/shared/lib/json';
import { validateInstanceDraft } from '@/shared/lib/validators/instance';
import type { AgentInstance } from '@/types/domain/instance';

export function useInstanceDetail(instanceId: string) {
  const [original, setOriginal] = useState<AgentInstance | null>(null);
  const [draft, setDraft] = useState<AgentInstance | null>(null);
  const [saving, setSaving] = useState(false);
  const [jsonErrors, setJsonErrors] = useState<Record<string, string | null>>({});

  useEffect(() => {
    instanceService.getById(instanceId).then((instance) => {
      setOriginal(instance);
      setDraft(instance ? structuredClone(instance) : null);
    });
  }, [instanceId]);

  const dirty = useMemo(() => JSON.stringify(original) !== JSON.stringify(draft), [original, draft]);

  async function save() {
    if (!draft) return;
    const errors = validateInstanceDraft(draft);
    if (errors.length > 0) {
      message.error(errors[0]);
      return;
    }
    setSaving(true);
    await instanceService.update(draft);
    setOriginal(structuredClone(draft));
    setSaving(false);
    message.success('Saved');
  }

  function reset() {
    setDraft(original ? structuredClone(original) : null);
  }

  function updateMetadata(key: keyof AgentInstance['metadata'], value: string) {
    setDraft((current) => current ? { ...current, metadata: { ...current.metadata, [key]: value } } : current);
  }

  function updateField(section: 'attributes' | 'variables', key: string, value: unknown) {
    setDraft((current) => current ? { ...current, [section]: { ...current[section], [key]: value } } : current);
  }

  function updateBindings(nextBindings: AgentInstance['bindings']) {
    setDraft((current) => current ? { ...current, bindings: nextBindings } : current);
  }

  function updateRuntimeBlock(key: 'memory' | 'activeGoals' | 'currentPlan' | 'extensions', raw: string) {
    try {
      const parsed = parseJsonBlock(raw);
      setJsonErrors((current) => ({ ...current, [key]: null }));
      setDraft((current) => current ? { ...current, [key]: parsed } : current);
    } catch (error) {
      setJsonErrors((current) => ({ ...current, [key]: (error as Error).message }));
    }
  }

  return { draft, dirty, saving, jsonErrors, save, reset, updateMetadata, updateField, updateBindings, updateRuntimeBlock, prettyJson };
}
```

`src/modules/instances/components/BindingTableEditor.tsx`
```tsx
import { Button, Form, Input, Modal, Space, Table } from 'antd';
import { useState } from 'react';
import type { AgentBinding } from '@/types/domain/instance';
import { buildBindingRows } from '@/modules/instances/adapters/instanceAdapters';

interface Props {
  value: Record<string, AgentBinding>;
  onChange: (value: Record<string, AgentBinding>) => void;
}

export function BindingTableEditor({ value, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [form] = Form.useForm();
  const rows = buildBindingRows(value);

  function edit(name?: string) {
    setEditingKey(name ?? null);
    form.setFieldsValue(name ? { name, ...value[name] } : { name: '', source: '' });
    setOpen(true);
  }

  async function submit() {
    const next = await form.validateFields();
    const { name, ...binding } = next;
    onChange({ ...value, [name]: binding });
    setOpen(false);
  }

  return (
    <>
      <Space style={{ marginBottom: 12 }}>
        <strong>Bindings</strong>
        <Button onClick={() => edit()}>Add</Button>
      </Space>
      <Table
        rowKey="name"
        pagination={false}
        dataSource={rows}
        columns={[
          { title: 'Variable', dataIndex: 'name' },
          { title: 'Source', dataIndex: 'source' },
          { title: 'Selector', dataIndex: 'selector' },
          { title: 'Transform', dataIndex: 'transform' },
          { title: 'Action', render: (_, row) => <Button onClick={() => edit(row.name)}>Edit</Button> },
        ]}
      />
      <Modal open={open} title="Binding" onCancel={() => setOpen(false)} onOk={submit}>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="Variable" rules={[{ required: true }]}>
            <Input disabled={!!editingKey} />
          </Form.Item>
          <Form.Item name="source" label="Source" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="path" label="Path">
            <Input />
          </Form.Item>
          <Form.Item name="topic" label="Topic">
            <Input />
          </Form.Item>
          <Form.Item name="selector" label="Selector">
            <Input />
          </Form.Item>
          <Form.Item name="transform" label="Transform">
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
```

`src/modules/instances/components/RuntimeJsonPanel.tsx`
```tsx
import { buildRuntimeJsonBlocks } from '@/modules/instances/adapters/instanceAdapters';
import { JsonBlockEditor } from '@/shared/components/JsonBlockEditor';
import type { AgentInstance } from '@/types/domain/instance';

interface Props {
  instance: AgentInstance;
  prettyJson: (value: unknown) => string;
  jsonErrors: Record<string, string | null>;
  onChange: (key: 'memory' | 'activeGoals' | 'currentPlan' | 'extensions', raw: string) => void;
}

export function RuntimeJsonPanel({ instance, prettyJson, jsonErrors, onChange }: Props) {
  return (
    <>
      {buildRuntimeJsonBlocks(instance).map((block) => (
        <div key={block.key} style={{ marginBottom: 16 }}>
          <h4>{block.label}</h4>
          <JsonBlockEditor
            label={block.label}
            value={prettyJson(block.value)}
            error={jsonErrors[block.key] ?? null}
            onChange={(value) => onChange(block.key as 'memory' | 'activeGoals' | 'currentPlan' | 'extensions', value)}
          />
        </div>
      ))}
    </>
  );
}
```

`src/modules/instances/components/InstanceEditorTabs.tsx`
```tsx
import { Form, Input, Tabs } from 'antd';
import { BindingTableEditor } from './BindingTableEditor';
import { RuntimeJsonPanel } from './RuntimeJsonPanel';
import type { AgentInstance } from '@/types/domain/instance';

interface Props {
  instance: AgentInstance;
  jsonErrors: Record<string, string | null>;
  prettyJson: (value: unknown) => string;
  onMetadataChange: (key: keyof AgentInstance['metadata'], value: string) => void;
  onFieldChange: (section: 'attributes' | 'variables', key: string, value: unknown) => void;
  onBindingsChange: (value: AgentInstance['bindings']) => void;
  onRuntimeChange: (key: 'memory' | 'activeGoals' | 'currentPlan' | 'extensions', raw: string) => void;
}

export function InstanceEditorTabs(props: Props) {
  return (
    <Tabs
      items={[
        {
          key: 'basic',
          label: 'Basic',
          children: (
            <Form layout="vertical">
              <Form.Item label="Name">
                <Input value={props.instance.metadata.name} onChange={(event) => props.onMetadataChange('name', event.target.value)} />
              </Form.Item>
              <Form.Item label="Title">
                <Input value={props.instance.metadata.title} onChange={(event) => props.onMetadataChange('title', event.target.value)} />
              </Form.Item>
            </Form>
          ),
        },
        {
          key: 'attributes',
          label: 'Attributes',
          children: Object.entries(props.instance.attributes).map(([key, value]) => (
            <Form.Item key={key} label={key}>
              <Input value={String(value ?? '')} onChange={(event) => props.onFieldChange('attributes', key, event.target.value)} />
            </Form.Item>
          )),
        },
        {
          key: 'variables',
          label: 'Variables',
          children: Object.entries(props.instance.variables).map(([key, value]) => (
            <Form.Item key={key} label={key}>
              <Input aria-label={key} value={String(value ?? '')} onChange={(event) => props.onFieldChange('variables', key, event.target.value)} />
            </Form.Item>
          )),
        },
        {
          key: 'bindings',
          label: 'Bindings',
          children: <BindingTableEditor value={props.instance.bindings} onChange={props.onBindingsChange} />,
        },
        {
          key: 'runtime-json',
          label: 'Runtime JSON',
          children: (
            <RuntimeJsonPanel
              instance={props.instance}
              prettyJson={props.prettyJson}
              jsonErrors={props.jsonErrors}
              onChange={props.onRuntimeChange}
            />
          ),
        },
      ]}
    />
  );
}
```

`src/pages/instances/InstanceDetailPage.tsx`
```tsx
import { Card, Descriptions, Spin } from 'antd';
import { useParams } from 'react-router-dom';
import { InstanceEditorTabs } from '@/modules/instances/components/InstanceEditorTabs';
import { useInstanceDetail } from '@/modules/instances/hooks/useInstanceDetail';
import { SaveActions } from '@/shared/components/SaveActions';

export function InstanceDetailPage() {
  const { instanceId = '' } = useParams();
  const { draft, dirty, saving, jsonErrors, save, reset, updateMetadata, updateField, updateBindings, updateRuntimeBlock, prettyJson } = useInstanceDetail(instanceId);

  if (!draft) return <Spin />;

  return (
    <Card title={draft.metadata.title} extra={<SaveActions dirty={dirty} saving={saving} onSave={save} onReset={reset} />}>
      <Descriptions size="small" column={2} style={{ marginBottom: 16 }}>
        <Descriptions.Item label="Instance ID">{draft.id}</Descriptions.Item>
        <Descriptions.Item label="Model">{draft.modelId}</Descriptions.Item>
        <Descriptions.Item label="State">{draft.state}</Descriptions.Item>
      </Descriptions>
      <InstanceEditorTabs
        instance={draft}
        jsonErrors={jsonErrors}
        prettyJson={prettyJson}
        onMetadataChange={updateMetadata}
        onFieldChange={updateField}
        onBindingsChange={updateBindings}
        onRuntimeChange={updateRuntimeBlock}
      />
    </Card>
  );
}
```

- [ ] **Step 5: Verify instance management flows**

Run:
```bash
npm run test -- --run src/pages/models/ModelDetailPage.instances.test.tsx src/pages/instances/InstanceDetailPage.test.tsx
npm run build
```

Expected:
- instance list and instance creation on model detail pass
- instance detail save flow passes
- build still succeeds

- [ ] **Step 6: Commit the instance management UI**

Run:
```bash
git add src/modules/instances src/pages/models/ModelDetailPage.tsx src/pages/instances/InstanceDetailPage.tsx
git commit -m "feat: add instance management workspace"
```

Expected: git creates a commit for model-scoped instances and the instance editor.

## Task 7: Add Unsaved-Changes Guard, Settings Reset, and Final Smoke Coverage

**Files:**
- Create: `src/shared/hooks/useUnsavedChangesGuard.ts`
- Modify: `src/pages/models/ModelDetailPage.tsx`
- Modify: `src/pages/instances/InstanceDetailPage.tsx`
- Modify: `src/pages/settings/SettingsPage.tsx`
- Test: `src/pages/settings/SettingsPage.test.tsx`
- Test: `src/app/smoke.test.tsx`

- [ ] **Step 1: Write failing guard and settings tests**

Create `src/pages/settings/SettingsPage.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SettingsPage } from './SettingsPage';

test('resets local model and instance data', async () => {
  const user = userEvent.setup();
  localStorage.setItem('agent-studio/models/v1', JSON.stringify([{ metadata: { name: 'temp', title: 'Temp' }, attributes: {}, variables: {} }]));
  localStorage.setItem('agent-studio/instances/v1', JSON.stringify([]));

  render(<SettingsPage />);

  await user.click(screen.getByRole('button', { name: 'Reset Local Data' }));

  expect(localStorage.getItem('agent-studio/models/v1')).not.toContain('temp');
});
```

Create `src/app/smoke.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { appRoutes } from './router';

test('navigates from models to settings', async () => {
  const router = createMemoryRouter(appRoutes, {
    initialEntries: ['/models'],
  });

  render(<RouterProvider router={router} />);

  expect(await screen.findByRole('heading', { name: 'Models' })).toBeInTheDocument();
  await router.navigate('/settings');
  expect(await screen.findByRole('heading', { name: 'Settings' })).toBeInTheDocument();
});
```

- [ ] **Step 2: Implement the unsaved-changes hook and integrate it into detail pages**

Write `src/shared/hooks/useUnsavedChangesGuard.ts`:
```ts
import { useEffect } from 'react';
import { useBlocker } from 'react-router-dom';

export function useUnsavedChangesGuard(isDirty: boolean, message = 'You have unsaved changes. Leave anyway?') {
  const blocker = useBlocker(({ currentLocation, nextLocation }) => {
    return isDirty && currentLocation.pathname !== nextLocation.pathname;
  });

  useEffect(() => {
    if (blocker.state !== 'blocked') return;

    const shouldLeave = window.confirm(message);
    if (shouldLeave) blocker.proceed();
    else blocker.reset();
  }, [blocker, message]);

  useEffect(() => {
    const handler = (event: BeforeUnloadEvent) => {
      if (!isDirty) return;
      event.preventDefault();
      event.returnValue = message;
    };

    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [isDirty, message]);
}
```

Modify both detail pages to call:
```tsx
useUnsavedChangesGuard(dirty);
```

right after the detail hook returns `dirty`.

- [ ] **Step 3: Implement the settings page reset action**

Write `src/pages/settings/SettingsPage.tsx`:
```tsx
import { Button, Card, Typography, message } from 'antd';
import { modelService } from '@/mocks/services/modelService';
import { instanceService } from '@/mocks/services/instanceService';

export function SettingsPage() {
  async function handleReset() {
    await Promise.all([modelService.reset(), instanceService.reset()]);
    message.success('Local data reset to seed state');
  }

  return (
    <Card>
      <Typography.Title level={2}>Settings</Typography.Title>
      <Typography.Paragraph>
        This page is intentionally small in the MVP and only exposes app info plus local data reset.
      </Typography.Paragraph>
      <Button danger onClick={handleReset}>
        Reset Local Data
      </Button>
    </Card>
  );
}
```

- [ ] **Step 4: Verify full smoke coverage**

Run:
```bash
npm run test -- --run
npm run build
```

Expected:
- all Vitest files pass
- build finishes successfully
- no unsaved-change or routing regressions appear in the smoke suite

- [ ] **Step 5: Commit the guard and reset flow**

Run:
```bash
git add src/shared/hooks/useUnsavedChangesGuard.ts src/pages/settings/SettingsPage.tsx src/pages/settings/SettingsPage.test.tsx src/app/smoke.test.tsx src/pages/models/ModelDetailPage.tsx src/pages/instances/InstanceDetailPage.tsx
git commit -m "feat: add guard rails and settings reset"
```

Expected: git creates a commit for unsaved-change protection and settings reset.

## Task 8: Final Verification Pass

**Files:**
- Modify: none expected unless verification fails

- [ ] **Step 1: Run targeted route checks in a browser-like dev session**

Run:
```bash
npm run dev
```

Manual checks:
- open `/models`
- open `/models/ladle`
- open `/models/ladle/instances/ladle_001`
- open `/settings`
- create one model and one instance
- refresh the browser and confirm both remain

Expected: all four routes render and local persistence survives refresh.

- [ ] **Step 2: Re-run automated verification before closing**

Run:
```bash
npm run test -- --run
npm run build
```

Expected:
- full test suite passes
- production build passes

- [ ] **Step 3: Summarize the delivered MVP**

Record in the final implementation summary:
- which routes exist
- which fields are structured editors
- which blocks remain JSON editors
- where `localStorage` keys are stored
- what was intentionally left out of scope

- [ ] **Step 4: Final commit**

Run:
```bash
git status --short
git add package.json package-lock.json tsconfig.json vite.config.ts vitest.setup.ts index.html src
git commit -m "feat: deliver agent studio frontend MVP"
```

Expected:
- working tree is clean after commit
- final commit captures the full MVP
