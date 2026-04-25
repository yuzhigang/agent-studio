# Lib Namespace Runtime Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `runtime.lib` work on the real world-load/runtime path by wiring a shared `LibRegistry` into `WorldRegistry`, `SandboxExecutor`, and `LibProxy`, while aligning default agent lib namespace with the script’s owning agent path.

**Architecture:** The change is a runtime wiring fix, not a new scripting model. First make registry namespace and reload semantics internally consistent, then thread a world-level `LibRegistry` through `WorldRegistry -> SandboxExecutor -> InstanceManager -> LibProxy`, then derive default namespace from the owning agent path instead of `model_name`, and finally lock down shared-import constraints and end-to-end tests.

**Tech Stack:** Python 3, pathlib, dataclasses, pytest

---

## File Map

- `src/runtime/lib/decorator.py`
  - Source of lib registration metadata; keep `name/module` semantics consistent with registry behavior.
- `src/runtime/lib/registry.py`
  - Scans `agents/`, registers `shared` and `group.agent` namespaces, and reloads changed modules.
- `src/runtime/lib/sandbox.py`
  - Imports shared modules into sandbox and enforces import restrictions.
- `src/runtime/lib/proxy.py`
  - Resolves `lib.*` calls against a default namespace plus explicit `shared`.
- `src/runtime/instance.py`
  - Runtime instance metadata; add internal field for owning agent namespace.
- `src/runtime/instance_manager.py`
  - Builds behavior context, owns `SandboxExecutor`, and constructs `LibProxy`.
- `src/runtime/world_registry.py`
  - Runtime composition root; scan world `agents/` and inject registry/sandbox into instance manager.
- `src/runtime/instance_loader.py`
  - Declaration scanner; source paths can be used to infer agent ownership.
- `tests/runtime/lib/test_registry.py`
  - Registry namespace and reload behavior.
- `tests/runtime/lib/test_proxy.py`
  - Default namespace and cross-agent rejection behavior.
- `tests/runtime/lib/test_integration.py`
  - End-to-end sandbox + proxy behavior from real fixture trees.
- `tests/runtime/test_world_registry_instance_loading.py`
  - Real world-load path for instance declarations and metadata.
- `tests/runtime/test_world_registry.py`
  - Bundle composition assertions.

### Task 1: Align lib registration metadata and reload semantics

**Files:**
- Modify: `src/runtime/lib/registry.py`
- Modify: `src/runtime/lib/decorator.py`
- Test: `tests/runtime/lib/test_registry.py`
- Test: `tests/runtime/lib/test_decorator.py`

- [ ] **Step 1: Write the failing tests for module override and reload cleanup**

```python
def test_registry_uses_module_override_in_registration_key(registry):
    registry._data.clear()

    @lib_function(name="getItems", module="dao")
    def get_items(args):
        return {"ok": True}

    module = type("M", (), {"get_items": get_items})
    registry._register_functions("logistics.ladle", Path("fake.py"), module)

    assert registry.lookup("logistics.ladle", "dao", "getItems")({}) == {"ok": True}


def test_reload_module_removes_old_module_override_keys(tmp_path):
    agents_dir = tmp_path / "agents"
    libs_dir = agents_dir / "logistics" / "ladle" / "libs"
    libs_dir.mkdir(parents=True)
    file_path = libs_dir / "adapter.py"
    file_path.write_text(
        "from src.runtime.lib.decorator import lib_function\n"
        "@lib_function(name='getItems', module='dao')\n"
        "def get_items(args):\n"
        "    return {'version': 1}\n",
        encoding="utf-8",
    )

    registry = LibRegistry()
    registry.scan(str(agents_dir))
    assert registry.lookup("logistics.ladle", "dao", "getItems")({}) == {"version": 1}

    file_path.write_text(
        "from src.runtime.lib.decorator import lib_function\n"
        "@lib_function(name='getItems', module='dao')\n"
        "def get_items(args):\n"
        "    return {'version': 2}\n",
        encoding="utf-8",
    )
    registry.reload_module(str(file_path))

    assert registry.lookup("logistics.ladle", "dao", "getItems")({}) == {"version": 2}
```

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run:

```bash
pytest tests/runtime/lib/test_registry.py tests/runtime/lib/test_decorator.py -v
```

Expected: FAIL because reload cleanup still keys by `py_file.stem` and/or registration metadata is not covered by tests.

- [ ] **Step 3: Implement the minimal metadata/reload fix**

`src/runtime/lib/registry.py`

```python
def _registered_prefixes_for_module(self, namespace: str, py_file: Path, module) -> set[str]:
    prefixes: set[str] = set()
    for attr_name in dir(module):
        obj = getattr(module, attr_name)
        meta = getattr(obj, "_lib_meta", None)
        if meta is not None:
            mod_name = meta["module"] or py_file.stem
            prefixes.add(f"{namespace}.{mod_name}.")
            continue
        if inspect.isclass(obj):
            for method_name in dir(obj):
                method = getattr(obj, method_name)
                meta = getattr(method, "_lib_meta", None)
                if meta is None:
                    continue
                mod_name = meta["module"] or py_file.stem
                prefixes.add(f"{namespace}.{mod_name}.")
    return prefixes


def reload_module(self, py_file_path: str):
    ...
    module = self._exec_module(namespace, py_file)
    prefixes = self._registered_prefixes_for_module(namespace, py_file, module)
    for key in list(self._registry.keys()):
        if any(key.startswith(prefix) for prefix in prefixes):
            del self._registry[key]
    self._register_functions(namespace, py_file, module)
```

Keep `lib_function(name=None, module=None)` untouched except for any tiny cleanup needed to keep metadata consistent.

- [ ] **Step 4: Run the tests again**

Run:

```bash
pytest tests/runtime/lib/test_registry.py tests/runtime/lib/test_decorator.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/runtime/lib/registry.py src/runtime/lib/decorator.py tests/runtime/lib/test_registry.py tests/runtime/lib/test_decorator.py
git commit -m "fix: align lib registration and reload semantics"
```

### Task 2: Thread a world-level LibRegistry into runtime composition

**Files:**
- Modify: `src/runtime/world_registry.py`
- Modify: `src/runtime/instance_manager.py`
- Test: `tests/runtime/test_world_registry.py`
- Test: `tests/runtime/test_world_registry_instance_loading.py`

- [ ] **Step 1: Write the failing runtime-composition tests**

```python
def test_load_world_bundle_contains_lib_registry(registry):
    registry.create_world("world-a")
    bundle = registry.load_world("world-a")

    assert bundle["lib_registry"] is not None
    assert bundle["instance_manager"]._sandbox.registry is bundle["lib_registry"]


def test_load_world_scans_world_agents_for_libs(registry):
    registry.create_world("test-world")
    world_dir = os.path.join(registry._base_dir, "test-world")
    libs_dir = os.path.join(world_dir, "agents", "logistics", "ladle", "libs")
    os.makedirs(libs_dir, exist_ok=True)
    with open(os.path.join(libs_dir, "dispatcher.py"), "w", encoding="utf-8") as f:
        f.write(
            "from src.runtime.lib.decorator import lib_function\n"
            "@lib_function()\n"
            "def get_candidates(args):\n"
            "    return {'candidates': []}\n"
        )

    bundle = registry.load_world("test-world")

    func = bundle["lib_registry"].lookup("logistics.ladle", "dispatcher", "get_candidates")
    assert func({}) == {"candidates": []}
```

- [ ] **Step 2: Run the focused tests and confirm failure**

Run:

```bash
pytest tests/runtime/test_world_registry.py tests/runtime/test_world_registry_instance_loading.py -v
```

Expected: FAIL because bundle does not yet expose a lib registry and no scan occurs during `load_world()`.

- [ ] **Step 3: Implement the minimal world-load wiring**

`src/runtime/world_registry.py`

```python
from src.runtime.lib.registry import LibRegistry
from src.runtime.lib.sandbox import SandboxExecutor

...
world_agents_dir = os.path.join(world_dir, "agents")
lib_registry = LibRegistry()
lib_registry.scan(world_agents_dir)
sandbox_executor = SandboxExecutor(registry=lib_registry)

im = InstanceManager(
    bus_reg,
    instance_store=store,
    model_loader=model_loader,
    sandbox_executor=sandbox_executor,
    world_state=world_state,
    world_event_emitter=None,
    trigger_registry=trigger_registry,
    alarm_manager=None,
)

bundle = {
    ...
    "lib_registry": lib_registry,
}
```

`src/runtime/instance_manager.py`

```python
def __init__(..., sandbox_executor: SandboxExecutor | None = None, ...):
    self._sandbox = sandbox_executor or SandboxExecutor()
```

Keep the constructor surface compatible with existing tests that manually pass a sandbox.

- [ ] **Step 4: Run the tests again**

Run:

```bash
pytest tests/runtime/test_world_registry.py tests/runtime/test_world_registry_instance_loading.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/runtime/world_registry.py src/runtime/instance_manager.py tests/runtime/test_world_registry.py tests/runtime/test_world_registry_instance_loading.py
git commit -m "feat: wire lib registry into world loading"
```

### Task 3: Make default lib namespace come from owning agent path

**Files:**
- Modify: `src/runtime/instance.py`
- Modify: `src/runtime/world_registry.py`
- Modify: `src/runtime/instance_manager.py`
- Modify: `src/runtime/instance_loader.py`
- Test: `tests/runtime/lib/test_integration.py`
- Test: `tests/runtime/test_world_registry_instance_loading.py`

- [ ] **Step 1: Write the failing tests for default namespace ownership**

```python
def test_instance_records_agent_namespace_from_declaration_path(registry):
    registry.create_world("test-world")
    world_dir = os.path.join(registry._base_dir, "test-world")

    model_dir = os.path.join(world_dir, "agents", "logistics", "ladle", "model")
    os.makedirs(model_dir, exist_ok=True)
    with open(os.path.join(model_dir, "index.yaml"), "w", encoding="utf-8") as f:
        f.write("metadata: {name: Ladle}\n")

    instances_dir = os.path.join(world_dir, "agents", "logistics", "ladle", "instances")
    os.makedirs(instances_dir, exist_ok=True)
    with open(os.path.join(instances_dir, "ladle-01.instance.yaml"), "w", encoding="utf-8") as f:
        f.write("id: ladle-01\nmodelId: ladle\n")

    bundle = registry.load_world("test-world")
    inst = bundle["instance_manager"].get("test-world", "ladle-01", scope="world")

    assert inst._agent_namespace == "logistics.ladle"


def test_behavior_context_lib_proxy_uses_agent_namespace(registry):
    registry.scan(os.path.join(FIXTURES, "agents"))
    proxy = LibProxy(default_namespace="logistics.ladle", registry=registry)
    result = proxy.dispatcher.get_candidates({})
    assert result == {"candidates": []}
```

- [ ] **Step 2: Run the focused tests and confirm failure**

Run:

```bash
pytest tests/runtime/lib/test_integration.py tests/runtime/test_world_registry_instance_loading.py -v
```

Expected: FAIL because instance objects do not yet carry owning agent namespace and default proxy namespace still uses `model_name`.

- [ ] **Step 3: Implement the minimal ownership propagation**

`src/runtime/instance.py`

```python
@dataclass
class Instance:
    ...
    _agent_namespace: str | None = field(default=None, repr=False)
```

`src/runtime/instance_loader.py`

```python
decl["_agent_namespace"] = ".".join(file_path.relative_to(agents_dir).parts[:2])
```

`src/runtime/world_registry.py`

```python
agent_namespace = decl.get("_agent_namespace")
im.create(
    ...,
    model_name=model_id,
    ...,
)
inst = im.get(world_id, instance_id, scope="world")
if inst is not None:
    inst._agent_namespace = agent_namespace
```

`src/runtime/instance_manager.py`

```python
default_namespace = getattr(instance, "_agent_namespace", None) or instance.model_name
lib_proxy = LibProxy(
    default_namespace=default_namespace,
    registry=getattr(self._sandbox, "registry", None),
    lib_context=lib_context,
)
```

The fallback to `instance.model_name` is only there for old tests that create bare instances without declaration metadata.

- [ ] **Step 4: Run the tests again**

Run:

```bash
pytest tests/runtime/lib/test_integration.py tests/runtime/test_world_registry_instance_loading.py -v
```

Expected: PASS, except the known external-network integration test may still depend on environment; if so, keep the namespace-focused tests green and note the network limitation.

- [ ] **Step 5: Commit**

```bash
git add src/runtime/instance.py src/runtime/world_registry.py src/runtime/instance_manager.py src/runtime/instance_loader.py tests/runtime/lib/test_integration.py tests/runtime/test_world_registry_instance_loading.py
git commit -m "feat: derive lib namespace from agent ownership"
```

### Task 4: Enforce shared-import and cross-agent boundaries

**Files:**
- Modify: `src/runtime/lib/proxy.py`
- Modify: `src/runtime/lib/sandbox.py`
- Test: `tests/runtime/lib/test_proxy.py`
- Test: `tests/runtime/lib/test_integration.py`

- [ ] **Step 1: Write the failing boundary tests**

```python
def test_sandbox_rejects_agent_specific_import_even_when_registry_loaded(registry):
    registry.scan(os.path.join(FIXTURES, "agents"))
    executor = SandboxExecutor(registry=registry)

    with pytest.raises(Exception, match="Import of 'dispatcher' is not allowed"):
        executor.execute("import dispatcher", {})


def test_proxy_rejects_cross_agent_full_path(registry):
    registry._data["machines.converter.planner.plan"] = lambda args: {"ok": True}
    proxy = LibProxy(default_namespace="logistics.ladle", registry=registry)

    with pytest.raises(LibNotFoundError, match="cross-agent"):
        proxy.machines.converter.planner.plan({})
```

- [ ] **Step 2: Run the focused tests and confirm failure**

Run:

```bash
pytest tests/runtime/lib/test_proxy.py tests/runtime/lib/test_integration.py -v
```

Expected: FAIL if cross-agent and shared-import boundaries are still incomplete in runtime execution.

- [ ] **Step 3: Implement the minimal boundary fixes**

`src/runtime/lib/proxy.py`

```python
if len(self._path) == 2:
    if not self._default_namespace:
        raise LibNotFoundError(".".join(self._path), details="no default namespace")
    candidates = [f"{self._default_namespace}.{self._path[0]}.{self._path[1]}"]
elif len(self._path) == 3 and self._path[0] == "shared":
    candidates = [".".join(self._path)]
else:
    raise LibNotFoundError(".".join(self._path), details="cross-agent lib calls are not allowed")
```

`src/runtime/lib/sandbox.py`

```python
def _build_shared_modules(registry):
    modules = {}
    for key, func in registry._data.items():
        parts = key.split(".")
        if len(parts) != 3 or parts[0] != "shared":
            continue
        _, mod_name, func_name = parts
        if mod_name in PRELOADED_MODULES:
            raise ScriptExecutionError(f"shared module name '{mod_name}' collides with preloaded module")
        ...
```

Do not expose agent-specific libs through Python `import`; keep them accessible only via `lib.*`.

- [ ] **Step 4: Run the tests again**

Run:

```bash
pytest tests/runtime/lib/test_proxy.py tests/runtime/lib/test_integration.py -v
```

Expected: PASS, aside from the known network-sensitive shared `http_get` case if the environment lacks outbound network.

- [ ] **Step 5: Commit**

```bash
git add src/runtime/lib/proxy.py src/runtime/lib/sandbox.py tests/runtime/lib/test_proxy.py tests/runtime/lib/test_integration.py
git commit -m "fix: enforce lib namespace access boundaries"
```

### Task 5: Run the real runtime sanity pass and update spec only if needed

**Files:**
- Modify: `docs/superpowers/specs/2026-04-26-lib-namespace-design.md` (only if implementation reveals a contradiction)

- [ ] **Step 1: Run the focused lib/runtime suite**

Run:

```bash
pytest tests/runtime/lib/test_registry.py tests/runtime/lib/test_proxy.py tests/runtime/lib/test_integration.py tests/runtime/test_world_registry.py tests/runtime/test_world_registry_instance_loading.py -v
```

Expected: PASS, except the known real-network fixture may still need a mocked environment.

- [ ] **Step 2: Run one broader runtime sanity pass**

Run:

```bash
pytest tests/runtime/test_instance_manager.py tests/runtime/test_world_registry.py tests/runtime/test_event_bus.py tests/runtime/test_alarm_integration.py -v
```

Expected: PASS

- [ ] **Step 3: If implementation contradicts the spec, update the spec inline**

Only make this change if needed. A valid clarification looks like:

```markdown
- shared module 名不得与常用标准库或预加载模块重名。
- shared module 名不得与 `PRELOADED_MODULES` 中的模块名重名；冲突在 registry/sandbox 装配阶段直接报错。
```

- [ ] **Step 4: Commit any doc clarification**

```bash
git add docs/superpowers/specs/2026-04-26-lib-namespace-design.md
git commit -m "docs: clarify lib namespace runtime constraints"
```

Skip this commit if no doc change was needed.

## Self-Review

### Spec coverage

- Sections 4 and 5 (namespace rules and usage rules) -> Tasks 2, 3, and 4
- Section 6 (runtime wiring) -> Task 2
- Section 7 (namespace source from owning agent path) -> Task 3
- Section 8 (registration key and reload semantics) -> Task 1
- Section 9 (sandbox shared import rules) -> Task 4
- Section 10 (tests) -> Tasks 1 through 5

No uncovered spec sections remain.

### Placeholder scan

- No `TBD`, `TODO`, or “similar to previous task” placeholders remain.
- Each task has concrete code or exact diff targets.
- Each verification step has exact commands and expected outcomes.

### Type consistency

- Registry namespace consistently uses `group.agent`.
- Runtime default namespace is consistently described as “owning agent namespace”.
- Shared import remains restricted to `shared`.
- Cross-agent direct lib calls remain rejected everywhere.
