# Hierarchical World State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `Instance` to hold `snapshot` (cached audit fields) and expose `world_state` as a property. Make `WorldState.snapshot()` return `dict[str, list[dict]]` grouped by `model_name`. Rename `InstanceManager.snapshot()` to `build_persist_dict()` and persist the structured `world_state`.

**Architecture:** Each `Instance` caches its audit field names in `_audit_fields` on first `_update_snapshot()` call, then incrementally updates `snapshot` dict. `world_state` is a read-only property that assembles metadata + snapshot. A `WorldState` aggregator groups active instances by `model_name`. The `InstanceManager` calls `_update_snapshot()` at known mutation points and injects the aggregated view into sandbox context.

**Tech Stack:** Python 3.13, pytest, existing runtime (`Instance`, `InstanceManager`, `EventBus`, `WorldRegistry`, `SceneManager`).

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/runtime/instance.py` | Modify | Add `snapshot` field, `_audit_fields` cache, `_update_snapshot()` method; `world_state` as property |
| `src/runtime/world_state.py` | Create | Aggregator that groups active instances by `model_name` |
| `src/runtime/instance_manager.py` | Modify | Rename `snapshot()` to `build_persist_dict()`; call `_update_snapshot()` at mutation points; inject `world_state` into sandbox context |
| `src/runtime/world_registry.py` | Modify | Wire `WorldState` into bundle, register `pre_publish_hook` |
| `src/runtime/scene_manager.py` | Modify | Call `_update_snapshot()` after property reconciliation |
| `tests/runtime/test_instance.py` | Modify | Tests for `Instance._update_snapshot()` and `world_state` property |
| `tests/runtime/test_world_state.py` | Create | Tests for `WorldState.snapshot()` grouping |
| `tests/runtime/test_instance_manager.py` | Modify | Tests for automatic `snapshot` updates and `build_persist_dict()` |
| `tests/runtime/test_world_registry.py` | Modify | Tests for `WorldRegistry` wiring |

---

### Task 1: Add `snapshot` and `world_state` property to `Instance`

**Files:**
- Modify: `src/runtime/instance.py`
- Test: `tests/runtime/test_instance.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/runtime/test_instance.py`:

```python
def test_instance_update_snapshot_with_audit_fields():
    inst = Instance(
        instance_id="ladle-001",
        model_name="ladle",
        world_id="proj-01",
        scope="world",
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
    inst._update_snapshot()
    assert inst.snapshot["temperature"] == 1500
    assert inst.snapshot["weight"] == 200
    assert inst.snapshot["capacity"] == 300
    assert inst.snapshot["loadRatio"] is None
    assert "operator" not in inst.snapshot
    assert "material" not in inst.snapshot

    # Verify world_state property assembles correctly
    ws = inst.world_state
    assert ws["id"] == "ladle-001"
    assert ws["state"] == "idle"
    assert ws["updated_at"] == "2024-01-01T00:00:00Z"
    assert ws["lifecycle_state"] == "active"
    assert ws["snapshot"]["temperature"] == 1500


def test_instance_update_snapshot_caches_audit_fields():
    inst = Instance(
        instance_id="ladle-001",
        model_name="ladle",
        world_id="proj-01",
        scope="world",
        variables={"temperature": 1500},
        model={
            "variables": {"temperature": {"type": "number", "audit": True}}
        },
    )
    assert not inst._audit_fields
    inst._update_snapshot()
    assert "temperature" in inst._audit_fields
    assert inst._audit_fields["temperature"] == "variables"

    # Change variable and update again - should use cached fields
    inst.variables["temperature"] = 1600
    inst._update_snapshot()
    assert inst.snapshot["temperature"] == 1600
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_instance.py::test_instance_update_snapshot_with_audit_fields tests/runtime/test_instance.py::test_instance_update_snapshot_caches_audit_fields -v`

Expected: `FAIL` with `AttributeError: 'Instance' object has no attribute '_update_snapshot'`

- [ ] **Step 3: Implement `snapshot`, `_audit_fields`, `_update_snapshot()`, and `world_state` property**

Modify `src/runtime/instance.py`:

```python
import copy
from dataclasses import dataclass, field


@dataclass
class Instance:
    instance_id: str
    model_name: str
    world_id: str
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
    snapshot: dict = field(default_factory=dict, repr=False)
    _audit_fields: dict = field(default_factory=dict, repr=False)

    @property
    def id(self) -> str:
        return self.instance_id

    @property
    def world_state(self) -> dict:
        return {
            "id": self.instance_id,
            "state": self.state.get("current"),
            "updated_at": self.state.get("enteredAt"),
            "lifecycle_state": self.lifecycle_state,
            "snapshot": copy.deepcopy(self.snapshot),
        }

    def deep_copy(self) -> "Instance":
        clone = copy.deepcopy(self)
        clone.snapshot = {}
        clone._audit_fields = {}
        return clone

    def _update_snapshot(self) -> dict:
        if not self._audit_fields and self.model:
            for name, defn in (self.model.get("variables") or {}).items():
                if defn.get("audit"):
                    self._audit_fields[name] = "variables"
            for name, defn in (self.model.get("attributes") or {}).items():
                if defn.get("audit"):
                    self._audit_fields[name] = "attributes"
            for name, defn in (self.model.get("derivedProperties") or {}).items():
                if defn.get("audit"):
                    self._audit_fields[name] = "derived"

        self.snapshot = {}
        for field_name, source in self._audit_fields.items():
            if source == "variables":
                self.snapshot[field_name] = copy.deepcopy(self.variables.get(field_name))
            elif source == "attributes":
                self.snapshot[field_name] = copy.deepcopy(self.attributes.get(field_name))
            elif source == "derived":
                self.snapshot[field_name] = copy.deepcopy(
                    self.variables.get(field_name, self.attributes.get(field_name))
                )
        return self.snapshot
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/test_instance.py::test_instance_update_snapshot_with_audit_fields tests/runtime/test_instance.py::test_instance_update_snapshot_caches_audit_fields -v`

Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add src/runtime/instance.py tests/runtime/test_instance.py
git commit -m "feat: add snapshot cache and world_state property on Instance"
```

---

### Task 2: Create `WorldState` aggregator

**Files:**
- Create: `src/runtime/world_state.py`
- Test: `tests/runtime/test_world_state.py`

- [ ] **Step 1: Write the failing test**

Create `tests/runtime/test_world_state.py`:

```python
import pytest
from src.runtime.world_state import WorldState
from src.runtime.instance_manager import InstanceManager


def test_world_state_snapshot_groups_by_model_name():
    mgr = InstanceManager()
    inst1 = mgr.create(
        world_id="proj-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="world",
        state={"current": "idle", "enteredAt": "2024-01-01T00:00:00Z"},
        variables={"temperature": 1500},
        model={
            "variables": {"temperature": {"type": "number", "audit": True}}
        },
    )
    inst1._update_snapshot()

    inst2 = mgr.create(
        world_id="proj-01",
        model_name="ladle",
        instance_id="ladle-002",
        scope="world",
        state={"current": "moving", "enteredAt": "2024-01-01T01:00:00Z"},
        variables={"temperature": 1600},
        model={
            "variables": {"temperature": {"type": "number", "audit": True}}
        },
    )
    inst2._update_snapshot()

    inst3 = mgr.create(
        world_id="proj-01",
        model_name="crane",
        instance_id="crane-001",
        scope="world",
        state={"current": "lifting", "enteredAt": "2024-01-01T00:30:00Z"},
        variables={"loadWeight": 5000},
        model={
            "variables": {"loadWeight": {"type": "number", "audit": True}}
        },
    )
    inst3._update_snapshot()

    # Create an archived instance that should be excluded
    inst4 = mgr.create(
        world_id="proj-01",
        model_name="ladle",
        instance_id="ladle-003",
        scope="world",
        state={"current": "idle", "enteredAt": "2024-01-01T02:00:00Z"},
        variables={"temperature": 1700},
        model={
            "variables": {"temperature": {"type": "number", "audit": True}}
        },
    )
    inst4._update_snapshot()
    mgr.transition_lifecycle("proj-01", "ladle-003", "archived")

    ws = WorldState(mgr, "proj-01")
    snapshot = ws.snapshot()

    assert "ladle" in snapshot
    assert "crane" in snapshot
    assert len(snapshot["ladle"]) == 2
    assert len(snapshot["crane"]) == 1

    ladle_ids = {item["id"] for item in snapshot["ladle"]}
    assert ladle_ids == {"ladle-001", "ladle-002"}
    assert snapshot["crane"][0]["id"] == "crane-001"

    # Verify structure
    item = snapshot["ladle"][0]
    assert "state" in item
    assert "updated_at" in item
    assert "lifecycle_state" in item
    assert "snapshot" in item
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_world_state.py::test_world_state_snapshot_groups_by_model_name -v`

Expected: `FAIL` with `ModuleNotFoundError: No module named 'src.runtime.world_state'`

- [ ] **Step 3: Implement `WorldState`**

Create `src/runtime/world_state.py`:

```python
import copy


class WorldState:
    def __init__(self, instance_manager, world_id: str):
        self._im = instance_manager
        self._world_id = world_id

    def snapshot(self) -> dict:
        result: dict[str, list[dict]] = {}
        for inst in self._im.list_by_world(self._world_id):
            if inst.lifecycle_state == "active" and inst.snapshot:
                model_name = inst.model_name
                result.setdefault(model_name, []).append(copy.deepcopy(inst.world_state))
        return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/test_world_state.py::test_world_state_snapshot_groups_by_model_name -v`

Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add src/runtime/world_state.py tests/runtime/test_world_state.py
git commit -m "feat: add WorldState aggregator with model_name grouping"
```

---

### Task 3: Wire `world_state` into `InstanceManager`

**Files:**
- Modify: `src/runtime/instance_manager.py`
- Test: `tests/runtime/test_instance_manager.py`

- [ ] **Step 1: Write failing tests for automatic snapshot updates**

Append to `tests/runtime/test_instance_manager.py`:

```python
def test_create_updates_snapshot():
    mgr = InstanceManager()
    inst = mgr.create(
        world_id="proj-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="world",
        state={"current": "idle", "enteredAt": "2024-01-01T00:00:00Z"},
        variables={"temperature": 1500},
        model={
            "variables": {"temperature": {"type": "number", "audit": True}}
        },
    )
    assert inst.snapshot["temperature"] == 1500
    assert inst.world_state["state"] == "idle"
    assert inst.world_state["snapshot"]["temperature"] == 1500


def test_run_script_updates_snapshot():
    bus_reg = EventBusRegistry()
    mgr = InstanceManager(bus_reg)
    inst = mgr.create(
        world_id="proj-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="world",
        state={"current": "idle", "enteredAt": "2024-01-01T00:00:00Z"},
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
    bus.publish("heat", {}, source="external", scope="world")
    assert inst.snapshot["temperature"] == 1600
    assert inst.world_state["snapshot"]["temperature"] == 1600


def test_transition_lifecycle_archived_clears_snapshot():
    mgr = InstanceManager()
    inst = mgr.create(
        world_id="proj-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="world",
        state={"current": "idle", "enteredAt": "2024-01-01T00:00:00Z"},
        variables={"temperature": 1500},
        model={
            "variables": {"temperature": {"type": "number", "audit": True}}
        },
    )
    assert inst.snapshot["temperature"] == 1500
    mgr.transition_lifecycle("proj-01", "ladle-001", "archived")
    assert inst.snapshot == {}


def test_behavior_context_includes_world_state():
    from src.runtime.world_state import WorldState

    mgr = InstanceManager()
    mgr.create(
        world_id="proj-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="world",
        state={"current": "idle", "enteredAt": "2024-01-01T00:00:00Z"},
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
    assert "ladle" in ctx["world_state"]
    assert ctx["world_state"]["ladle"][0]["snapshot"]["temperature"] == 1500


def test_build_persist_dict_includes_world_state():
    class FakeStore:
        def __init__(self):
            self.saved = {}
        def save_instance(self, world_id, instance_id, scope, snapshot):
            self.saved[(world_id, instance_id, scope)] = snapshot

    store = FakeStore()
    mgr = InstanceManager(instance_store=store)
    mgr.create(
        world_id="proj-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="world",
        state={"current": "idle", "enteredAt": "2024-01-01T00:00:00Z"},
        variables={"temperature": 1500},
        model={
            "variables": {"temperature": {"type": "number", "audit": True}}
        },
    )
    snap = store.saved[("proj-01", "ladle-001", "world")]
    assert "world_state" in snap
    assert snap["world_state"]["id"] == "ladle-001"
    assert snap["world_state"]["snapshot"]["temperature"] == 1500


def test_lazy_load_restores_world_state():
    class FakeStore:
        def load_instance(self, world_id, instance_id, scope):
            return {
                "world_id": world_id,
                "instance_id": instance_id,
                "scope": scope,
                "model_name": "ladle",
                "model_version": "1.0",
                "attributes": {},
                "state": {"current": "idle", "enteredAt": "2024-01-01T00:00:00Z"},
                "variables": {"temperature": 1500},
                "links": {},
                "memory": {},
                "audit": {"version": 1},
                "lifecycle_state": "active",
                "world_state": {
                    "id": instance_id,
                    "state": "idle",
                    "updated_at": "2024-01-01T00:00:00Z",
                    "lifecycle_state": "active",
                    "snapshot": {"temperature": 1500},
                },
                "updated_at": "2024-01-01T00:00:00+00:00",
            }

    store = FakeStore()
    mgr = InstanceManager(instance_store=store)
    inst = mgr.get("proj-01", "ladle-001", scope="world")
    assert inst is not None
    assert inst.world_state["id"] == "ladle-001"
    assert inst.world_state["snapshot"]["temperature"] == 1500
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/runtime/test_instance_manager.py::test_create_updates_snapshot tests/runtime/test_instance_manager.py::test_run_script_updates_snapshot tests/runtime/test_instance_manager.py::test_transition_lifecycle_archived_clears_snapshot tests/runtime/test_instance_manager.py::test_behavior_context_includes_world_state tests/runtime/test_instance_manager.py::test_build_persist_dict_includes_world_state tests/runtime/test_instance_manager.py::test_lazy_load_restores_world_state -v`

Expected: `FAIL` due to missing `_world_state` wiring and `_update_snapshot()` calls

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

2. Rename `snapshot` to `build_persist_dict` and include `world_state`:

```python
    def build_persist_dict(self, inst: Instance) -> dict:
        return {
            "model_name": inst.model_name,
            "model_version": inst.model_version,
            "attributes": inst.attributes or {},
            "state": inst.state or {"current": None, "enteredAt": None},
            "variables": inst.variables or {},
            "links": inst.links or {},
            "memory": inst.memory or {},
            "audit": inst.audit or {"version": 0, "updatedAt": None, "lastEventId": None},
            "lifecycle_state": inst.lifecycle_state,
            "world_state": inst.world_state or {},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
```

3. Update `_save_to_store` to use the new name:

```python
    def _save_to_store(self, inst: Instance):
        if self._store is not None:
            self._store.save_instance(
                inst.world_id, inst.instance_id, inst.scope, self.build_persist_dict(inst)
            )
```

4. In `create`, after `self._register_instance(inst)`:

```python
        inst._update_snapshot()
        self._save_to_store(inst)
        return inst
```

5. In `get`, inside the lazy-load block (after setting `inst.model` and before `self._register_instance(inst)`):

```python
            inst.snapshot = copy.deepcopy(snapshot.get("world_state", {}).get("snapshot", {}))
            inst._audit_fields = {}
```

Then after `self._register_instance(inst)` and before `return inst`:

```python
            inst._update_snapshot()
```

6. In `copy_for_scene`, after `clone.scope = f"scene:{scene_id}"` and before `self._save_to_store(clone)`:

```python
            clone._update_snapshot()
```

7. In `transition_lifecycle`, reorder so `_update_snapshot()` happens before `_save_to_store`:

```python
    def transition_lifecycle(self, world_id, instance_id, new_state, scope="world"):
        inst = self.get(world_id, instance_id, scope)
        if inst is None:
            return False
        inst.lifecycle_state = new_state
        inst._update_snapshot()
        self._save_to_store(inst)
        if new_state == "archived":
            with self._lock:
                self._instances.pop(self._make_key(world_id, instance_id, scope), None)
            self._unregister_instance(inst)
            inst.snapshot = {}
            inst._audit_fields = {}
        return True
```

8. In `_execute_action`, inside `action_type == "runScript"` block:

```python
        if action_type == "runScript":
            script = action.get("script", "")
            engine = action.get("scriptEngine", "python")
            if engine == "python" and script:
                try:
                    self._sandbox.execute(script, context)
                except Exception:
                    # Swallow sandbox errors to avoid breaking the event bus
                    pass
            instance._update_snapshot()
```

9. In `_build_behavior_context`, before return:

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

Run: `pytest tests/runtime/test_instance_manager.py::test_create_updates_snapshot tests/runtime/test_instance_manager.py::test_run_script_updates_snapshot tests/runtime/test_instance_manager.py::test_transition_lifecycle_archived_clears_snapshot tests/runtime/test_instance_manager.py::test_behavior_context_includes_world_state tests/runtime/test_instance_manager.py::test_build_persist_dict_includes_world_state tests/runtime/test_instance_manager.py::test_lazy_load_restores_world_state -v`

Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add src/runtime/instance_manager.py tests/runtime/test_instance_manager.py
git commit -m "feat: wire structured world_state into InstanceManager lifecycle and sandbox context"
```

---

### Task 4: Wire `WorldState` into `WorldRegistry`

**Files:**
- Modify: `src/runtime/world_registry.py`
- Test: `tests/runtime/test_world_registry.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/runtime/test_world_registry.py`:

```python
def test_load_world_wires_world_state_and_pre_publish_hook(registry):
    registry.create_world("ladle-proj")

    bundle = registry.load_world("ladle-proj")
    assert "world_state" in bundle
    ws = bundle["world_state"]
    im = bundle["instance_manager"]

    inst = im.create(
        world_id="ladle-proj",
        model_name="ladle",
        instance_id="ladle-001",
        scope="world",
        state={"current": "idle", "enteredAt": "2024-01-01T00:00:00Z"},
        variables={"temperature": 1500},
        model={
            "variables": {"temperature": {"type": "number", "audit": True}}
        },
    )
    # snapshot should already be computed by InstanceManager.create
    assert inst.snapshot["temperature"] == 1500

    # Publish an event from the instance and verify pre_publish_hook updates snapshot
    bus = bundle["event_bus_registry"].get_or_create("ladle-proj")
    inst.variables["temperature"] = 1600
    bus.publish("heat", {}, source="ladle-001", scope="world")
    assert inst.snapshot["temperature"] == 1600

    # Verify snapshot structure
    snapshot = ws.snapshot()
    assert "ladle" in snapshot
    assert len(snapshot["ladle"]) == 1
    assert snapshot["ladle"][0]["id"] == "ladle-001"
    assert snapshot["ladle"][0]["snapshot"]["temperature"] == 1600
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_world_registry.py::test_load_world_wires_world_state_and_pre_publish_hook -v`

Expected: `FAIL` because `WorldRegistry` does not yet create `WorldState`

- [ ] **Step 3: Modify `WorldRegistry`**

Modify `src/runtime/world_registry.py`:

1. Add import:

```python
from src.runtime.world_state import WorldState
```

2. In `load_world`, after creating `bus_reg` and before creating `im`:

```python
            world_state = WorldState(None, world_id)

            im = InstanceManager(
                bus_reg,
                instance_store=store,
                world_state=world_state,
            )
            world_state._im = im

            bus = bus_reg.get_or_create(world_id)
            # This hook only updates the publisher (source) instance.
            # Consumers that run scripts will update their own snapshot
            # inside InstanceManager._execute_action.
            def world_event_hook(event_type, payload, source, scope, target):
                inst = im.get(world_id, source, scope=scope)
                if inst is not None:
                    inst._update_snapshot()
            bus.add_pre_publish_hook(world_event_hook)
```

3. Add `world_state` to the bundle:

```python
            bundle = {
                "world_id": world_id,
                "world_yaml": world_yaml,
                "store": store,
                "event_bus_registry": bus_reg,
                "instance_manager": im,
                "scene_manager": scene_mgr,
                "state_manager": state_mgr,
                "metric_store": metric_store,
                "world_state": world_state,
                "lock": world_lock,
                "_registry": self,
                "force_stop_on_shutdown": False,
            }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/test_world_registry.py::test_load_world_wires_world_state_and_pre_publish_hook -v`

Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add src/runtime/world_registry.py tests/runtime/test_world_registry.py
git commit -m "feat: wire WorldState into WorldRegistry with pre_publish_hook"
```

---

### Task 5: Update `SceneManager` to update `snapshot` during reconciliation

**Files:**
- Modify: `src/runtime/scene_manager.py`

- [ ] **Step 1: Modify `_reconcile_properties`**

Change `src/runtime/scene_manager.py`:

```python
    def _reconcile_properties(self, instances: list):
        """Stub property reconciliation: derivedProperties will be recomputed here."""
        # TODO: recompute derivedProperties based on current variables/attributes
        for inst in instances:
            inst._update_snapshot()
```

- [ ] **Step 2: Commit**

```bash
git add src/runtime/scene_manager.py
git commit -m "feat: update snapshot after scene property reconciliation"
```

---

### Task 6: Run the full test suite for affected components

**Files:**
- (no file changes, verification only)

- [ ] **Step 1: Run all related tests**

Run: `pytest tests/runtime/test_instance.py tests/runtime/test_world_state.py tests/runtime/test_instance_manager.py tests/runtime/test_world_registry.py tests/runtime/test_scene_manager.py -v`

Expected: All tests pass

- [ ] **Step 2: Run the broader test suite**

Run: `pytest tests/ -v`

Expected: All tests pass

- [ ] **Step 3: Final commit if any fixes were needed**

If no fixes needed, this step is a no-op. If fixes were needed, commit them with a clear message.

---

## Plan Review

### Spec Coverage Check

| Spec Requirement | Task |
|-----------------|------|
| `Instance.snapshot` 缓存 audit 字段 | Task 1 |
| `Instance.world_state` as read-only property | Task 1 |
| `Instance._update_snapshot()` 增量更新 | Task 1 |
| `WorldState.snapshot()` returns `dict[str, list[dict]]` grouped by `model_name` | Task 2 |
| `InstanceManager.build_persist_dict()` persists `world_state` | Task 3 |
| `InstanceManager.get()` restores `world_state` from store | Task 3 |
| Trigger `_update_snapshot()` at create, script execution, lifecycle transition | Task 3 |
| Inject `world_state` into sandbox context | Task 3 |
| `WorldRegistry` wiring with `pre_publish_hook` | Task 4 |
| `SceneManager._reconcile_properties()` triggers `_update_snapshot()` | Task 5 |
| `InstanceManager.snapshot()` renamed to `build_persist_dict()` | Task 3 |

**No gaps found.**

### Placeholder Scan

- No "TBD", "TODO", "implement later", or "fill in details" found (except the existing stub TODO in `_reconcile_properties` which is unchanged)
- No vague requirements like "add appropriate error handling"
- No "Similar to Task N" references
- Every step has complete code blocks

### Type Consistency Check

- `Instance.snapshot` / `Instance._audit_fields` / `Instance._update_snapshot()` consistent across all tasks
- `Instance.world_state` property consistent
- `WorldState.snapshot()` returns `dict[str, list[dict]]` consistently
- `InstanceManager.__init__` signature includes `world_state` parameter consistently
- Field names `updated_at` (not `enteredAt`) used consistently throughout
- `InstanceManager.build_persist_dict()` name consistent
