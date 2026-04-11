# Agent Studio Config Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current split Models / Model Detail / Instance Detail flow with a compact four-pane configuration workbench that keeps menu, model list, instance list, and instance detail visible in one desktop-first workspace.

**Architecture:** Keep route-driven state for deep links, but render the `Models` area as a single workbench page that reads the selected model and instance from URL params. Reuse the existing model and instance editor hooks, wrap them in slimmer workbench components, and keep list panes read-only except for focused creation entry points.

**Tech Stack:** React 18, React Router 7, Ant Design 5, Vitest, Testing Library

---

## File Structure

### Existing files to modify

- `src/shared/layout/AppLayout.tsx`
  Makes the left rail ultra narrow and adds `Data` and `Events` placeholders while preserving `Settings`.
- `src/app/router.tsx`
  Redirects `/` to the default workbench route and keeps model / instance URL params usable inside the same page shell.
- `src/pages/models/ModelsPage.tsx`
  Converts the current card list page into the four-pane workbench container.
- `src/pages/models/ModelsPage.test.tsx`
  Verifies the workbench renders models and supports creation inside the new layout.
- `src/pages/models/ModelDetailPage.test.tsx`
  Refocuses model tests from standalone page editing to model-selection and workbench synchronization.
- `src/pages/models/ModelDetailPage.instances.test.tsx`
  Refocuses instance-creation coverage into the workbench flow.
- `src/pages/instances/InstanceDetailPage.test.tsx`
  Moves instance-detail save coverage into the embedded detail pane.
- `src/app/router.test.tsx`
  Verifies redirects and route rendering still work after consolidation.
- `src/app/App.test.tsx`
  Verifies the default app entry shows the new shell.
- `src/styles/globals.css`
  Adds the compact four-pane layout and responsive fallback styles.

### New files to create

- `src/modules/workbench/components/ConfigWorkbench.tsx`
  Top-level four-pane workspace for the `Models` domain.
- `src/modules/workbench/components/CompactModelList.tsx`
  Dense model list column with selection state and `+ New`.
- `src/modules/workbench/components/CompactInstanceList.tsx`
  Dense instance list column with empty state and stronger selection state.
- `src/modules/workbench/components/InstanceDetailWorkbench.tsx`
  Compact instance detail header and tabbed editor container.
- `src/modules/workbench/components/WorkbenchPlaceholder.tsx`
  Shared empty / unselected placeholders for instance list and detail pane.
- `src/modules/workbench/hooks/useConfigWorkbench.ts`
  Coordinates models, instances, selected IDs, create actions, and route-aware selections.
- `src/modules/workbench/components/ConfigWorkbench.test.tsx`
  End-to-end workbench behavior coverage across model select, instance select, and empty states.

## Task 1: Convert App Shell to the New Navigation Frame

**Files:**
- Modify: `src/shared/layout/AppLayout.tsx`
- Modify: `src/app/router.tsx`
- Modify: `src/app/router.test.tsx`
- Modify: `src/app/App.test.tsx`

- [ ] **Step 1: Write the failing navigation tests**

```tsx
test('redirects / to the models workbench and renders compact navigation', async () => {
  renderWithRoute('/');

  expect(await screen.findByRole('link', { name: 'Models' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Data' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Events' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Prefs' })).toBeInTheDocument();
  expect(await screen.findByText('Studio')).toBeInTheDocument();
});

test('renders the routed app shell with the workbench visible by default', async () => {
  render(<App />);

  expect(await screen.findByRole('link', { name: 'Models' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Data' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Events' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Prefs' })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `npm test -- src/app/router.test.tsx src/app/App.test.tsx --runInBand`

Expected: FAIL because `Data`, `Events`, `Prefs`, and the compact shell branding do not exist yet.

- [ ] **Step 3: Update the shell and route configuration**

```tsx
const menuItems = [
  { key: '/models', label: <Link to="/models">Models</Link> },
  { key: '/data', label: <Link to="/data">Data</Link> },
  { key: '/events', label: <Link to="/events">Events</Link> },
  { key: '/settings', label: <Link to="/settings">Prefs</Link> },
];

function getSelectedMenuKey(pathname: string): string {
  if (pathname.startsWith('/settings')) return '/settings';
  if (pathname.startsWith('/events')) return '/events';
  if (pathname.startsWith('/data')) return '/data';
  return '/models';
}

<Layout.Sider width={88} theme="light" className="app-rail">
  <div className="app-rail__brand">Studio</div>
  <Menu mode="inline" selectedKeys={[getSelectedMenuKey(location.pathname)]} items={menuItems} />
</Layout.Sider>
```

```tsx
children: [
  { index: true, element: <Navigate to="/models" replace /> },
  { path: 'models', element: <ModelsPage /> },
  { path: 'models/:modelId', element: <ModelsPage /> },
  { path: 'models/:modelId/instances/:instanceId', element: <ModelsPage /> },
  { path: 'data', element: <Navigate to="/models" replace /> },
  { path: 'events', element: <Navigate to="/models" replace /> },
  { path: 'settings', element: <SettingsPage /> },
]
```

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `npm test -- src/app/router.test.tsx src/app/App.test.tsx --runInBand`

Expected: PASS with both test files green.

- [ ] **Step 5: Commit**

```bash
git add src/shared/layout/AppLayout.tsx src/app/router.tsx src/app/router.test.tsx src/app/App.test.tsx
git commit -m "feat: add compact app rail for config workbench"
```

## Task 2: Add a Route-Aware Workbench State Hook

**Files:**
- Create: `src/modules/workbench/hooks/useConfigWorkbench.ts`
- Create: `src/modules/workbench/components/ConfigWorkbench.test.tsx`

- [ ] **Step 1: Write the failing workbench state test**

```tsx
test('loads models, derives selected model and selected instance from the route', async () => {
  renderWorkbench('/models/ladle/instances/ladle_001');

  expect(await screen.findByRole('heading', { name: 'Models' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Customer Support' })).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByRole('button', { name: 'prod-cn-01' })).toHaveAttribute('aria-pressed', 'true');
});
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `npm test -- src/modules/workbench/components/ConfigWorkbench.test.tsx --runInBand`

Expected: FAIL because the workbench module and route-aware selection hook do not exist.

- [ ] **Step 3: Implement the state hook**

```ts
export function useConfigWorkbench(modelIdParam?: string, instanceIdParam?: string) {
  const [models, setModels] = useState<AgentModel[]>([]);
  const [instances, setInstances] = useState<AgentInstance[]>([]);
  const [loading, setLoading] = useState(true);

  const selectedModel = models.find((model) => model.metadata.name === modelIdParam) ?? models[0] ?? null;
  const selectedInstance =
    instances.find((instance) => instance.id === instanceIdParam) ?? instances[0] ?? null;

  // load models on mount, then load instances whenever selectedModel changes
  // expose createModel and createInstance actions that append to local state
}
```

- [ ] **Step 4: Run the focused test to verify it passes**

Run: `npm test -- src/modules/workbench/components/ConfigWorkbench.test.tsx --runInBand`

Expected: PASS with selected model and instance derived from the route.

- [ ] **Step 5: Commit**

```bash
git add src/modules/workbench/hooks/useConfigWorkbench.ts src/modules/workbench/components/ConfigWorkbench.test.tsx
git commit -m "feat: add route-aware config workbench state"
```

## Task 3: Build the Compact Model and Instance Columns

**Files:**
- Create: `src/modules/workbench/components/CompactModelList.tsx`
- Create: `src/modules/workbench/components/CompactInstanceList.tsx`
- Create: `src/modules/workbench/components/WorkbenchPlaceholder.tsx`
- Modify: `src/modules/workbench/components/ConfigWorkbench.test.tsx`

- [ ] **Step 1: Write the failing list interaction tests**

```tsx
test('switches the instance list when the user selects a different model', async () => {
  const user = userEvent.setup();
  renderWorkbench('/models/ladle');

  await user.click(await screen.findByRole('button', { name: 'Risk Monitor' }));

  expect(await screen.findByRole('heading', { name: 'Instances' })).toBeInTheDocument();
  expect(screen.getByText('No instances yet')).toBeInTheDocument();
});

test('shows a detail placeholder before an instance is selected', async () => {
  renderWorkbench('/models/ladle');

  expect(await screen.findByText('Select an instance to edit')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `npm test -- src/modules/workbench/components/ConfigWorkbench.test.tsx --runInBand`

Expected: FAIL because the compact list components and placeholders do not exist.

- [ ] **Step 3: Implement the compact left columns**

```tsx
export function CompactModelList({ models, selectedModelId, onSelect, onCreate }: CompactModelListProps) {
  return (
    <section className="workbench-pane workbench-pane--list" aria-label="Models">
      <header className="workbench-pane__header">
        <h2>Models</h2>
        <CreateModelModal existingNames={models.map((model) => model.metadata.name)} onCreate={onCreate} />
      </header>
      <div className="workbench-list">
        {models.map((model) => (
          <button
            key={model.metadata.name}
            type="button"
            aria-pressed={model.metadata.name === selectedModelId}
            className="workbench-list__item"
            onClick={() => onSelect(model.metadata.name)}
          >
            <span>{model.metadata.title}</span>
            <span>{model.instancesCount} inst.</span>
          </button>
        ))}
      </div>
    </section>
  );
}
```

```tsx
export function CompactInstanceList({ instances, selectedInstanceId, onSelect }: CompactInstanceListProps) {
  if (instances.length === 0) {
    return <WorkbenchPlaceholder title="Instances" description="No instances yet" />;
  }

  return (
    <section className="workbench-pane workbench-pane--list" aria-label="Instances">
      <header className="workbench-pane__header">
        <h2>Instances</h2>
      </header>
      <div className="workbench-list">
        {instances.map((instance) => (
          <button
            key={instance.id}
            type="button"
            aria-pressed={instance.id === selectedInstanceId}
            className="workbench-list__item workbench-list__item--instance"
            onClick={() => onSelect(instance.id)}
          >
            <span>{instance.id}</span>
            <span>{instance.state}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `npm test -- src/modules/workbench/components/ConfigWorkbench.test.tsx --runInBand`

Expected: PASS with model switching and empty-state coverage green.

- [ ] **Step 5: Commit**

```bash
git add src/modules/workbench/components/CompactModelList.tsx src/modules/workbench/components/CompactInstanceList.tsx src/modules/workbench/components/WorkbenchPlaceholder.tsx src/modules/workbench/components/ConfigWorkbench.test.tsx
git commit -m "feat: add compact model and instance columns"
```

## Task 4: Embed the Instance Detail Editor in the Right Pane

**Files:**
- Create: `src/modules/workbench/components/InstanceDetailWorkbench.tsx`
- Create: `src/modules/workbench/components/ConfigWorkbench.tsx`
- Modify: `src/pages/models/ModelsPage.tsx`
- Modify: `src/pages/models/ModelsPage.test.tsx`
- Modify: `src/pages/models/ModelDetailPage.test.tsx`
- Modify: `src/pages/models/ModelDetailPage.instances.test.tsx`
- Modify: `src/pages/instances/InstanceDetailPage.test.tsx`

- [ ] **Step 1: Write the failing embedded-detail tests**

```tsx
test('renders the workbench instead of the old card list page', async () => {
  render(
    <MemoryRouter initialEntries={['/models/ladle/instances/ladle_001']}>
      <ModelsPage />
    </MemoryRouter>,
  );

  expect(await screen.findByRole('heading', { name: 'Instances' })).toBeInTheDocument();
  expect(screen.getByText('prod-cn-01')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument();
});

test('edits instance variables from the embedded detail pane and saves them', async () => {
  renderWorkbench('/models/ladle/instances/ladle_001');

  fireEvent.click(await screen.findByRole('tab', { name: 'Variables' }));
  fireEvent.change(screen.getByLabelText('processStatus'), { target: { value: 'transport_ready' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save' }));

  await waitFor(() => {
    expect(screen.getByText('Saved')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `npm test -- src/pages/models/ModelsPage.test.tsx src/pages/models/ModelDetailPage.test.tsx src/pages/models/ModelDetailPage.instances.test.tsx src/pages/instances/InstanceDetailPage.test.tsx --runInBand`

Expected: FAIL because the workbench does not yet host the instance editor and the old standalone page assumptions still hold.

- [ ] **Step 3: Implement the workbench page and embedded detail panel**

```tsx
export function ModelsPage() {
  const { modelId = '', instanceId = '' } = useParams();

  return <ConfigWorkbench modelIdParam={modelId} instanceIdParam={instanceId} />;
}
```

```tsx
export function InstanceDetailWorkbench({ modelId, instanceId }: InstanceDetailWorkbenchProps) {
  const detail = useInstanceDetail(modelId, instanceId);
  useUnsavedChangesGuard(detail.dirty);

  if (!instanceId) {
    return <WorkbenchPlaceholder title="Instance Detail" description="Select an instance to edit" />;
  }

  return (
    <section className="workbench-pane workbench-pane--detail">
      <header className="workbench-detail__header">
        <div>
          <h2>{detail.draft?.id}</h2>
          <p>{detail.draft?.modelId} / {detail.draft?.state}</p>
        </div>
        <SaveActions dirty={detail.dirty} saving={detail.saving} onSave={detail.save} onReset={detail.reset} />
      </header>
      <InstanceEditorTabs
        instance={detail.draft!}
        jsonDrafts={detail.jsonDrafts}
        jsonErrors={detail.jsonErrors}
        onMetadataChange={detail.updateMetadata}
        onFieldChange={detail.updateField}
        onBindingsChange={detail.updateBindings}
        onRuntimeChange={detail.updateRuntimeBlock}
      />
    </section>
  );
}
```

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `npm test -- src/pages/models/ModelsPage.test.tsx src/pages/models/ModelDetailPage.test.tsx src/pages/models/ModelDetailPage.instances.test.tsx src/pages/instances/InstanceDetailPage.test.tsx --runInBand`

Expected: PASS with creation and embedded save flows green.

- [ ] **Step 5: Commit**

```bash
git add src/modules/workbench/components/InstanceDetailWorkbench.tsx src/modules/workbench/components/ConfigWorkbench.tsx src/pages/models/ModelsPage.tsx src/pages/models/ModelsPage.test.tsx src/pages/models/ModelDetailPage.test.tsx src/pages/models/ModelDetailPage.instances.test.tsx src/pages/instances/InstanceDetailPage.test.tsx
git commit -m "feat: embed instance detail inside models workbench"
```

## Task 5: Apply Compact Styling and Responsive Fallback

**Files:**
- Modify: `src/styles/globals.css`
- Modify: `src/modules/workbench/components/ConfigWorkbench.tsx`
- Modify: `src/modules/workbench/components/ConfigWorkbench.test.tsx`

- [ ] **Step 1: Write the failing layout test**

```tsx
test('renders the four-pane workbench structure with compact pane labels', async () => {
  renderWorkbench('/models/ladle/instances/ladle_001');

  expect(await screen.findByTestId('config-workbench')).toHaveClass('config-workbench');
  expect(screen.getByLabelText('Models')).toBeInTheDocument();
  expect(screen.getByLabelText('Instances')).toBeInTheDocument();
  expect(screen.getByLabelText('Instance Detail')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `npm test -- src/modules/workbench/components/ConfigWorkbench.test.tsx --runInBand`

Expected: FAIL because the workbench root classes and pane labels are not fully wired.

- [ ] **Step 3: Add the compact layout classes**

```css
.config-workbench {
  display: grid;
  grid-template-columns: 208px 208px minmax(0, 1fr);
  min-height: calc(100vh - 48px);
  background: #f3f6fa;
  border: 1px solid #d6dee8;
  border-radius: 18px;
  overflow: hidden;
}

.workbench-pane {
  min-width: 0;
  background: #fff;
}

.workbench-pane--list {
  padding: 10px;
  border-right: 1px solid #d6dee8;
}

.workbench-pane--detail {
  padding: 12px;
}

@media (max-width: 1100px) {
  .config-workbench {
    grid-template-columns: 1fr;
  }
}
```

```tsx
<section data-testid="config-workbench" className="config-workbench">
  <CompactModelList ... />
  <CompactInstanceList ... />
  <InstanceDetailWorkbench ... />
</section>
```

- [ ] **Step 4: Run the focused test to verify it passes**

Run: `npm test -- src/modules/workbench/components/ConfigWorkbench.test.tsx --runInBand`

Expected: PASS with structural assertions green.

- [ ] **Step 5: Commit**

```bash
git add src/styles/globals.css src/modules/workbench/components/ConfigWorkbench.tsx src/modules/workbench/components/ConfigWorkbench.test.tsx
git commit -m "style: add compact config workbench layout"
```

## Task 6: Run Full Regression Coverage

**Files:**
- Modify: none

- [ ] **Step 1: Run the targeted regression suite**

Run: `npm test -- src/app/router.test.tsx src/app/App.test.tsx src/pages/models/ModelsPage.test.tsx src/pages/models/ModelDetailPage.test.tsx src/pages/models/ModelDetailPage.instances.test.tsx src/pages/instances/InstanceDetailPage.test.tsx src/modules/workbench/components/ConfigWorkbench.test.tsx --runInBand`

Expected: PASS with all related workbench, routing, and editor tests green.

- [ ] **Step 2: Run the full test suite**

Run: `npm test -- --runInBand`

Expected: PASS with the whole Vitest suite green.

- [ ] **Step 3: Build the application**

Run: `npm run build`

Expected: PASS with Vite production build output in `dist/`.

- [ ] **Step 4: Commit the verified work**

```bash
git add src docs
git commit -m "feat: ship agent studio config workbench"
```

## Self-Review

### Spec coverage

- Four-pane left-to-right flow: covered in Tasks 2 through 5.
- Ultra-narrow menu and additional top-level destinations: covered in Task 1.
- Model list and instance list role separation: covered in Task 3.
- Embedded detail editor with save / reset and tabs: covered in Task 4.
- Compact visual direction and responsive fallback: covered in Task 5.
- Empty states for no models, no instances, and no selection: covered in Tasks 2 and 3.

### Placeholder scan

- No `TODO`, `TBD`, or deferred implementation wording remains.
- Each task includes concrete files, code, commands, and expected outcomes.

### Type consistency

- The plan consistently uses `modelIdParam`, `instanceIdParam`, `selectedModelId`, and `selectedInstanceId`.
- The workbench flow assumes existing `useInstanceDetail`, `CreateModelModal`, `CreateInstanceModal`, and `SaveActions` reuse instead of introducing new editor APIs.
