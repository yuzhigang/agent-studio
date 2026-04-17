# Instance World State Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `world_state` derived property to every `Instance`, automatically maintained by the runtime, and expose a project-level aggregated `world_state` snapshot to behavior scripts running in the sandbox.

**Architecture:** Each `Instance` computes its own `world_state` (a flattened projection of `audit: true` fields from `variables`, `attributes`, and `derivedProperties`). A lightweight `WorldState` class aggregates active instances on demand. The `InstanceManager` triggers recomputation after instance creation, lifecycle transitions, script execution, and before any event is published.

**Tech Stack:** Python 3.13, pytest, existing runtime (`Instance`, `InstanceManager`, `EventBus`, `ProjectRegistry`, `SceneManager`).

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/runtime/instance.py` | Modify | Add `world_state` field and `recompute_world_state()` method to `Instance` dataclass |
| `src/runtime/world_state.py` | Create | Lightweight aggregator that collects `world_state` from all active instances in a project |
| `src/runtime/instance_manager.py` | Modify | Trigger `recompute_world_state()` at lifecycle points and inject aggregated `world_state` into sandbox behavior context |
| `src/runtime/project_registry.py` | Modify | Wire `WorldState` into the project bundle and register an `EventBus.pre_publish_hook` to recompute the source instance before events are published |
| `src/runtime/scene_manager.py` | Modify | Trigger `recompute_world_state()` after property reconciliation during scene start |
| `tests/runtime/test_instance.py` | Modify | Add tests for `Instance.recompute_world_state()` |
| `tests/runtime/test_world_state.py` | Create | Add tests for `WorldState.snapshot()` aggregation |
| `tests/runtime/test_instance_manager.py` | Modify | Add tests for automatic `world_state` updates via `InstanceManager` |

---

### Task 1: Add `world_state` to `Instance`

**Files:**
- Modify: `src/runtime/instance.py`
- Test: `tests/runtime/test_instance.py`

- [ ] **Step 1: Write the failing test**

```python
def test_instance_recompute_world_state_with_audit_fields():
    inst = Instance(
        instance_id="ladle-001",
        model_name="ladle",
        project_id="proj-01",
        scope="project",
        state={"current": "idle", "enteredAt": "2024-01-01T00:00:00Z"},
        variables={"temperature": 1500, "weight": 200},
        attributes={"capacity": 300},
        model={
            "variables": {
                "temperature": {"type": "number", "audit": True},
                "weight": {"type": "number", "audit": True},
                "operator": {"type": "string"},
            },
            "attributes": {
                "capacity": {"type": "number", "audit": True},
                "material": {"type": "string"},
            },
            "derivedProperties": {
                "loadRatio": {"type": "number", "audit": True},
            },
        },
    )
    inst.recompute_world_state()
    assert inst.world_state["model_name"] == "ladle"
    assert inst.world_state["state"] == {"current": "idle", "enteredAt": "2024-01-01T00:00:00Z"}
    assert inst.world_state["temperature"] == 1500
    assert inst.world_state["weight"] == 200
    assert inst.world_state["capacity"] == 300
    assert inst.world_state["loadRatio"] is None
    assert "operator" not in inst.world_state
    assert "material" not in inst.world_state
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_instance.py::test_instance_recompute_world_state_with_audit_fields -v`

Expected: `FAIL` with `AttributeError: 'Instance' object has no attribute 'recompute_world_state'`

- [ ] **Step 3: Implement `world_state` field and `recompute_world_state()`**

Modify `src/runtime/instance.py`:

```python
import copy
from dataclasses import dataclass, field


@dataclass
class Instance:
    instance_id: str
    model_name: str
    project_id: str
    scope: str
    model_version: str | None = field(default=None)
    attributes: dict = field(default_factory=dict)
    variables: dict = field(default_factory=dict)
    links: dict = field(default_factory=dict)
    memory: dict = field(default_factory=dict)
    state: dict = field(default_factory=lambda: {"current": None, "enteredAt": None})
    audit: dict = field(default_factory=lambda: {"version": 0, "updatedAt": None, "lastEventId": None})
    lifecycle_state: str = field(default="active")
    model: dict | None = field(default=None, repr=False)
    world_state: dict = field(default_factory=dict, repr=False)

    @property
    def id(self) -> str:
        return self.instance_id

    def deep_copy(self) -> "Instance":
        clone = copy.deepcopy(self)
        clone.world_state = {}
        return clone

    def recompute_world_state(self) -> dict:
        model = self.model or {}
        projection = {
            "model_name": self.model_name,
            "state": copy.deepcopy(self.state),
        }

        for name, defn in (model.get("variables") or {}).items():
            if defn.get("audit"):
                projection[name] = copy.deepcopy(self.variables.get(name))
        for name, defn in (model.get("attributes") or {}).items():
            if defn.get("audit"):
                projection[name] = copy.deepcopy(self.attributes.get(name))
        for name, defn in (model.get("derivedProperties") or {}).items():
            if defn.get("audit"):
                # Invariant: derived property values must be materialized into
                # variables or attributes before recompute_world_state() is called.
                projection[name] = copy.deepcopy(
                    self.variables.get(name, self.attributes.get(name))
                )

        self.world_state = projection
        return projection
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/test_instance.py::test_instance_recompute_world_state_with_audit_fields -v`

Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add src/runtime/instance.py tests/runtime/test_instance.py
git commit -m "feat: add world_state as a derived property on Instance"
```

---

### Task 2: Create `WorldState` aggregator

**Files:**
- Create: `src/runtime/world_state.py`
- Test: `tests/runtime/test_world_state.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from src.runtime.world_state import WorldState
from src.runtime.instance_manager import InstanceManager


def test_world_state_snapshot_aggregates_active_instances():
    mgr = InstanceManager()
    inst1 = mgr.create(
        project_id="proj-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="project",
        state={"current": "idle"},
        variables={"temperature": 1500},
        model={
            "variables": {"temperature": {"type": "number", "audit": True}}
        },
    )
    inst1.recompute_world_state()

    inst2 = mgr.create(
        project_id="proj-01",
        model_name="ladle",
        instance_id="ladle-002",
        scope="project",
        state={"current": "moving"},
        variables={"temperature": 1600},
        model={
            "variables": {"temperature": {"type": "number", "audit": True}}
        },
    )
    inst2.recompute_world_state()

    # Create an archived instance that should be excluded
    inst3 = mgr.create(
        project_id="proj-01",
        model_name="ladle",
        instance_id="ladle-003",
        scope="project",
        state={"current": "idle"},
        variables={"temperature": 1700},
        model={
            "variables": {"temperature": {"type": "number", "audit": True}}
        },
    )
    inst3.recompute_world_state()
    mgr.transition_lifecycle("proj-01", "ladle-003", "archived")

    ws = WorldState(mgr, "proj-01")
    snapshot = ws.snapshot()

    assert "ladle-001" in snapshot
    assert "ladle-002" in snapshot
    assert "ladle-003" not in snapshot
    assert snapshot["ladle-001"]["temperature"] == 1500
    assert snapshot["ladle-002"]["temperature"] == 1600
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_world_state.py::test_world_state_snapshot_aggregates_active_instances -v`

Expected: `FAIL` with `ModuleNotFoundError: No module named 'src.runtime.world_state'`

- [ ] **Step 3: Implement `WorldState`**

Create `src/runtime/world_state.py`:

```python
import copy


class WorldState:
    def __init__(self, instance_manager, project_id: str):
        self._im = instance_manager
        self._project_id = project_id

    def snapshot(self) -> dict:
        result = {}
        for inst in self._im.list_by_project(self._project_id):
            if inst.lifecycle_state == "active" and inst.world_state:
                result[inst.id] = copy.deepcopy(inst.world_state)
        return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/test_world_state.py::test_world_state_snapshot_aggregates_active_instances -v`

Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add src/runtime/world_state.py tests/runtime/test_world_state.py
git commit -m "feat: add WorldState aggregator for project-level snapshots"
```

---

### Task 3: Wire `WorldState` into `InstanceManager`

**Files:**
- Modify: `src/runtime/instance_manager.py`
- Test: `tests/runtime/test_instance_manager.py`

- [ ] **Step 1: Write failing tests for automatic world_state updates**

Append to `tests/runtime/test_instance_manager.py`:

```python
def test_create_recomputes_world_state():
    mgr = InstanceManager()
    inst = mgr.create(
        project_id="proj-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="project",
        state={"current": "idle"},
        variables={"temperature": 1500},
        model={
            "variables": {"temperature": {"type": "number", "audit": True}}
        },
    )
    assert inst.world_state["temperature"] == 1500


def test_run_script_recomputes_world_state():
    bus_reg = EventBusRegistry()
    mgr = InstanceManager(bus_reg)
    inst = mgr.create(
        project_id="proj-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="project",
        variables={"temperature": 1500},
        model={
            "variables": {"temperature": {"type": "number", "audit": True}},
            "behaviors": {
                "updateTemp": {
                    "trigger": {"type": "event", "name": "heat"},
                    "actions": [
                        {
                            "type": "runScript",
                            "scriptEngine": "python",
                            "script": "this.variables.temperature = 1600",
                        }
                    ],
                }
            },
        },
    )
    bus = bus_reg.get_or_create("proj-01")
    bus.publish("heat", {}, source="external", scope="project")
    assert inst.world_state["temperature"] == 1600


def test_transition_lifecycle_archived_clears_world_state():
    mgr = InstanceManager()
    inst = mgr.create(
        project_id="proj-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="project",
        state={"current": "idle"},
        variables={"temperature": 1500},
        model={
            "variables": {"temperature": {"type": "number", "audit": True}}
        },
    )
    assert inst.world_state["temperature"] == 1500
    mgr.transition_lifecycle("proj-01", "ladle-001", "archived")
    assert inst.world_state == {}


def test_behavior_context_includes_world_state():
    from src.runtime.world_state import WorldState

    mgr = InstanceManager()
    mgr.create(
        project_id="proj-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="project",
        state={"current": "idle"},
        variables={"temperature": 1500},
        model={
            "variables": {"temperature": {"type": "number", "audit": True}}
        },
    )
    ws = WorldState(mgr, "proj-01")
    mgr._world_state = ws

    inst = mgr.get("proj-01", "ladle-001")
    ctx = mgr._build_behavior_context(inst, {"foo": "bar"}, "external")
    assert "world_state" in ctx
    assert ctx["world_state"]["ladle-001"]["temperature"] == 1500
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/runtime/test_instance_manager.py::test_create_recomputes_world_state tests/runtime/test_instance_manager.py::test_run_script_recomputes_world_state tests/runtime/test_instance_manager.py::test_transition_lifecycle_archived_clears_world_state tests/runtime/test_instance_manager.py::test_behavior_context_includes_world_state -v`

Expected: `FAIL` due to missing `_world_state` wiring and recompute calls

- [ ] **Step 3: Modify `InstanceManager`**

Modify `src/runtime/instance_manager.py`:

1. Update `__init__` signature and body:

```python
class InstanceManager:
    def __init__(
        self,
        event_bus_registry=None,
        instance_store=None,
        model_loader: Callable[[str], dict | None] | None = None,
        sandbox_executor: SandboxExecutor | None = None,
        world_state=None,
    ):
        self._instances: dict[tuple[str, str], Instance] = {}
        self._lock = threading.Lock()
        self._bus_reg = event_bus_registry
        self._store = instance_store
        self._model_loader = model_loader
        self._sandbox = sandbox_executor or SandboxExecutor()
        self._world_state = world_state
```

2. In `create`, after `self._register_instance(inst)`:

```python
        inst.recompute_world_state()
        self._save_to_store(inst)
        return inst
```

3. In `get`, inside the lazy-load block (after `self._register_instance(inst)` and before `return inst`):

```python
            inst.recompute_world_state()
```

4. In `copy_for_scene`, after `clone.scope = f"scene:{scene_id}"` and before `self._save_to_store(clone)`:

```python
            clone.recompute_world_state()
```

5. In `transition_lifecycle`, reorder so `recompute_world_state()` happens before `_save_to_store`:

```python
    def transition_lifecycle(self, project_id, instance_id, new_state, scope="project"):
        inst = self.get(project_id, instance_id, scope)
        if inst is None:
            return False
        inst.lifecycle_state = new_state
        inst.recompute_world_state()
        self._save_to_store(inst)
        if new_state == "archived":
            with self._lock:
                self._instances.pop(self._make_key(project_id, instance_id, scope), None)
            self._unregister_instance(inst)
            inst.world_state = {}
        return True
```

6. In `_execute_action`, inside `action_type == "runScript"` block:

```python
        if action_type == "runScript":
            script = action.get("script", "")
            engine = action.get("scriptEngine", "python")
            if engine == "python" and script:
                try:
                    self._sandbox.execute(script, context)
                except Exception:
                    pass
            instance.recompute_world_state()
```

7. In `_build_behavior_context`, before return:

```python
        world_state = {}
        if self._world_state is not None:
            world_state = self._world_state.snapshot()

        return {
            "this": _wrap_instance(instance),
            "payload": _DictProxy(payload),
            "source": source,
            "dispatch": dispatch,
            "world_state": _DictProxy(world_state),
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/runtime/test_instance_manager.py::test_create_recomputes_world_state tests/runtime/test_instance_manager.py::test_run_script_recomputes_world_state tests/runtime/test_instance_manager.py::test_transition_lifecycle_archived_clears_world_state tests/runtime/test_instance_manager.py::test_behavior_context_includes_world_state -v`

Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add src/runtime/instance_manager.py tests/runtime/test_instance_manager.py
git commit -m "feat: wire world_state into InstanceManager lifecycle and sandbox context"
```

---

### Task 4: Wire `WorldState` into `ProjectRegistry`

**Files:**
- Modify: `src/runtime/project_registry.py`
- Test: `tests/runtime/test_project_registry.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/runtime/test_project_registry.py`:

```python
def test_load_project_wires_world_state_and_pre_publish_hook(tmp_path):
    from src.runtime.project_registry import ProjectRegistry
    from src.runtime.instance_manager import InstanceManager

    registry = ProjectRegistry(base_dir=str(tmp_path))
    registry.create_project("ladle-proj")

    bundle = registry.load_project("ladle-proj")
    assert "world_state" in bundle
    ws = bundle["world_state"]
    im = bundle["instance_manager"]

    inst = im.create(
        project_id="ladle-proj",
        model_name="ladle",
        instance_id="ladle-001",
        scope="project",
        state={"current": "idle"},
        variables={"temperature": 1500},
        model={
            "variables": {"temperature": {"type": "number", "audit": True}}
        },
    )
    # world_state should already be computed by InstanceManager.create
    assert inst.world_state["temperature"] == 1500

    # Publish an event from the instance and verify pre_publish_hook recomputes world_state
    bus = bundle["event_bus_registry"].get_or_create("ladle-proj")
    inst.variables["temperature"] = 1600
    bus.publish("heat", {}, source="ladle-001", scope="project")
    assert inst.world_state["temperature"] == 1600

    # Verify snapshot
    snapshot = ws.snapshot()
    assert snapshot["ladle-001"]["temperature"] == 1600
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_project_registry.py::test_load_project_wires_world_state_and_pre_publish_hook -v`

Expected: `FAIL` because `ProjectRegistry` does not yet create `WorldState`

- [ ] **Step 3: Modify `ProjectRegistry`**

Modify `src/runtime/project_registry.py`:

1. Add import:

```python
from src.runtime.world_state import WorldState
```

2. In `load_project`, after creating `bus_reg` and before creating `im`:

```python
            world_state = WorldState(None, project_id)

            im = InstanceManager(
                bus_reg,
                instance_store=store,
                world_state=world_state,
            )
            world_state._im = im

            bus = bus_reg.get_or_create(project_id)
            # This hook only recomputes the publisher (source) instance.
            # Consumers that run scripts will recompute their own world_state
            # inside InstanceManager._execute_action.
            def world_event_hook(event_type, payload, source, scope, target):
                inst = im.get(project_id, source, scope=scope)
                if inst is not None:
                    inst.recompute_world_state()
            bus.add_pre_publish_hook(world_event_hook)
```

3. Add `world_state` to the bundle:

```python
            bundle = {
                "project_id": project_id,
                "project_yaml": project_yaml,
                "store": store,
                "event_bus_registry": bus_reg,
                "instance_manager": im,
                "scene_manager": scene_mgr,
                "state_manager": state_mgr,
                "metric_store": metric_store,
                "world_state": world_state,
                "lock": project_lock,
                "_registry": self,
                "force_stop_on_shutdown": False,
            }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/test_project_registry.py::test_load_project_wires_world_state_and_pre_publish_hook -v`

Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add src/runtime/project_registry.py tests/runtime/test_project_registry.py
git commit -m "feat: wire WorldState into ProjectRegistry with pre_publish_hook"
```

---

### Task 5: Update `SceneManager` to recompute `world_state` during reconciliation

**Files:**
- Modify: `src/runtime/scene_manager.py`

- [ ] **Step 1: Modify `_reconcile_properties`**

Change `src/runtime/scene_manager.py`:

```python
    def _reconcile_properties(self, instances: list):
        """Stub property reconciliation: derivedProperties will be recomputed here."""
        # TODO: recompute derivedProperties based on current variables/attributes
        for inst in instances:
            inst.recompute_world_state()
```

- [ ] **Step 2: Commit**

```bash
git add src/runtime/scene_manager.py
git commit -m "feat: recompute world_state after scene property reconciliation"
```

---

### Task 6: Run the full test suite for affected components

**Files:**
- (no file changes, verification only)

- [ ] **Step 1: Run all related tests**

Run: `pytest tests/runtime/test_instance.py tests/runtime/test_world_state.py tests/runtime/test_instance_manager.py tests/runtime/test_project_registry.py tests/runtime/test_scene_manager.py -v`

Expected: All tests pass

- [ ] **Step 2: Final commit if any fixes were needed**

If no fixes needed, this step is a no-op. If fixes were needed, commit them with a clear message.

---

## Plan Review

After completing the plan document, dispatch the plan-document-reviewer subagent with the plan path and this spec context: "Add a per-instance `world_state` derived property that aggregates `audit: true` fields, maintained automatically by the runtime, and expose it to sandbox behavior scripts via a project-level `WorldState` snapshot."
