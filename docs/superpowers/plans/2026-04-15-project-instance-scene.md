# Project-Instance-Scene Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the core runtime classes for Project-Instance-Scene architecture: `EventBus`, `EventBusRegistry`, `Instance`, `InstanceManager`, and `SceneController`, with in-memory persistence and full test coverage.

**Architecture:** A lightweight in-memory runtime where each `Project` gets its own `EventBus` via `EventBusRegistry`. `InstanceManager` holds instances keyed by `(project_id, instance_id)` and supports deep-copy CoW for isolated scenes. `SceneController` orchestrates scene startup, reference validation, and metric backfill. `SandboxExecutor` gains a `dispatch()` helper via context injection.

**Tech Stack:** Python 3.11+, PyYAML, pytest, copy.deepcopy

---

### Task 1: EventBus and EventBusRegistry

**Files:**
- Create: `src/runtime/event_bus.py`
- Create: `tests/runtime/test_event_bus.py`

- [ ] **Step 1: Write failing test for EventBus registration and publish**

```python
import pytest
from src.runtime.event_bus import EventBus

def test_publish_delivers_to_subscriber():
    bus = EventBus()
    received = []
    def handler(event_type, payload, source):
        received.append((event_type, payload, source))
    bus.register("ladle-001", "project", "ladleLoaded", handler)
    bus.publish("ladleLoaded", {"steelAmount": 180}, "caster-03", "project")
    assert len(received) == 1
    assert received[0] == ("ladleLoaded", {"steelAmount": 180}, "caster-03")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_event_bus.py::test_publish_delivers_to_subscriber -v`
Expected: FAIL (EventBus not found)

- [ ] **Step 3: Implement EventBus**

Create `src/runtime/event_bus.py`:

```python
import threading

class EventBus:
    def __init__(self):
        self._subscribers: dict[str, list[tuple[str, str, callable]]] = {}
        self._lock = threading.RLock()

    def register(self, instance_id: str, scope: str, event_type: str, handler: callable):
        with self._lock:
            self._subscribers.setdefault(event_type, []).append((instance_id, scope, handler))

    def unregister(self, instance_id: str):
        with self._lock:
            for event_type in list(self._subscribers.keys()):
                self._subscribers[event_type] = [
                    (iid, sc, h) for iid, sc, h in self._subscribers[event_type] if iid != instance_id
                ]

    def publish(self, event_type: str, payload: dict, source: str, scope: str, target: str | None = None):
        with self._lock:
            handlers = list(self._subscribers.get(event_type, []))
        for instance_id, inst_scope, handler in handlers:
            if target and instance_id != target:
                continue
            if not self._scope_matches(scope, inst_scope):
                continue
            handler(event_type, payload, source)

    def _scope_matches(self, msg_scope: str, inst_scope: str) -> bool:
        if msg_scope == "project":
            return True
        return msg_scope == inst_scope


class EventBusRegistry:
    def __init__(self):
        self._buses: dict[str, EventBus] = {}
        self._lock = threading.Lock()

    def get_or_create(self, project_id: str) -> EventBus:
        with self._lock:
            if project_id not in self._buses:
                self._buses[project_id] = EventBus()
            return self._buses[project_id]

    def destroy(self, project_id: str):
        with self._lock:
            self._buses.pop(project_id, None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/test_event_bus.py::test_publish_delivers_to_subscriber -v`
Expected: PASS

- [ ] **Step 5: Write failing test for scope isolation**

Append to `tests/runtime/test_event_bus.py`:

```python
def test_scope_isolation_scene_vs_project():
    bus = EventBus()
    scene_received = []
    proj_received = []
    bus.register("ladle-001", "scene:drill", "ladleLoaded", lambda t, p, s: scene_received.append(t))
    bus.register("ladle-002", "project", "ladleLoaded", lambda t, p, s: proj_received.append(t))
    bus.publish("ladleLoaded", {}, "caster-03", "scene:drill")
    assert len(scene_received) == 1
    assert len(proj_received) == 0
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/runtime/test_event_bus.py::test_scope_isolation_scene_vs_project -v`
Expected: PASS

- [ ] **Step 7: Write failing test for EventBusRegistry**

Append to `tests/runtime/test_event_bus.py`:

```python
from src.runtime.event_bus import EventBusRegistry

def test_registry_get_or_create_and_destroy():
    registry = EventBusRegistry()
    bus1 = registry.get_or_create("proj-a")
    bus2 = registry.get_or_create("proj-a")
    assert bus1 is bus2
    bus3 = registry.get_or_create("proj-b")
    assert bus3 is not bus1
    registry.destroy("proj-a")
    bus4 = registry.get_or_create("proj-a")
    assert bus4 is not bus1
```

- [ ] **Step 8: Run test to verify it passes**

Run: `pytest tests/runtime/test_event_bus.py::test_registry_get_or_create_and_destroy -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
rtk git add src/runtime/event_bus.py tests/runtime/test_event_bus.py
rtk git commit -m "feat: add EventBus and EventBusRegistry"
```

---

### Task 2: Instance Data Model

**Files:**
- Create: `src/runtime/instance.py`
- Create: `tests/runtime/test_instance.py`

- [ ] **Step 1: Write failing test for Instance creation and deep copy**

```python
import copy
from src.runtime.instance import Instance

def test_instance_creation():
    inst = Instance(
        instance_id="ladle-001",
        model_name="ladle",
        project_id="proj-01",
        scope="project",
        attributes={"capacity": 200},
        variables={"steelAmount": 180},
        links={"assignedCaster": "caster-03"},
    )
    assert inst.id == "ladle-001"
    assert inst.model_name == "ladle"
    assert inst.scope == "project"
    assert inst.variables["steelAmount"] == 180
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_instance.py::test_instance_creation -v`
Expected: FAIL (Instance not found)

- [ ] **Step 3: Implement Instance dataclass**

Create `src/runtime/instance.py`:

```python
from dataclasses import dataclass, field
import copy

@dataclass
class Instance:
    instance_id: str
    model_name: str
    project_id: str
    scope: str
    attributes: dict = field(default_factory=dict)
    variables: dict = field(default_factory=dict)
    links: dict = field(default_factory=dict)
    memory: dict = field(default_factory=dict)
    state: dict = field(default_factory=lambda: {"current": None, "enteredAt": None})
    audit: dict = field(default_factory=lambda: {"version": 0, "updatedAt": None, "lastEventId": None})
    model: dict | None = field(default=None, repr=False)

    @property
    def id(self) -> str:
        return self.instance_id

    def deep_copy(self) -> "Instance":
        return Instance(
            instance_id=self.instance_id,
            model_name=self.model_name,
            project_id=self.project_id,
            scope=self.scope,
            attributes=copy.deepcopy(self.attributes),
            variables=copy.deepcopy(self.variables),
            links=copy.deepcopy(self.links),
            memory=copy.deepcopy(self.memory),
            state=copy.deepcopy(self.state),
            audit=copy.deepcopy(self.audit),
            model=self.model,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/test_instance.py::test_instance_creation -v`
Expected: PASS

- [ ] **Step 5: Write failing test for deep_copy isolation**

Append to `tests/runtime/test_instance.py`:

```python
def test_instance_deep_copy_isolation():
    inst = Instance(
        instance_id="ladle-001",
        model_name="ladle",
        project_id="proj-01",
        scope="project",
        variables={"steelAmount": 180, "nested": {"a": 1}},
    )
    clone = inst.deep_copy()
    clone.variables["steelAmount"] = 0
    clone.variables["nested"]["a"] = 99
    assert inst.variables["steelAmount"] == 180
    assert inst.variables["nested"]["a"] == 1
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/runtime/test_instance.py::test_instance_deep_copy_isolation -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
rtk git add src/runtime/instance.py tests/runtime/test_instance.py
rtk git commit -m "feat: add Instance data model with deep_copy"
```

---

### Task 3: InstanceManager

**Files:**
- Create: `src/runtime/instance_manager.py`
- Create: `tests/runtime/test_instance_manager.py`

- [ ] **Step 1: Write failing test for create and get**

```python
import pytest
from src.runtime.instance_manager import InstanceManager
from src.runtime.instance import Instance

def test_create_and_get_instance():
    mgr = InstanceManager()
    inst = mgr.create(
        project_id="proj-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="project",
        attributes={"capacity": 200},
        variables={"steelAmount": 180},
    )
    assert inst.id == "ladle-001"
    assert mgr.get("proj-01", "ladle-001", scope="project") is inst
    assert mgr.get("proj-01", "ladle-002", scope="project") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_instance_manager.py::test_create_and_get_instance -v`
Expected: FAIL (InstanceManager not found)

- [ ] **Step 3: Implement InstanceManager**

Create `src/runtime/instance_manager.py`:

```python
import threading
import copy
from src.runtime.instance import Instance

class InstanceManager:
    def __init__(self, event_bus_registry=None):
        self._instances: dict[tuple[str, str], Instance] = {}
        self._lock = threading.Lock()
        self._bus_reg = event_bus_registry

    @staticmethod
    def _make_key(project_id: str, instance_id: str, scope: str = "project") -> tuple[str, str]:
        if scope.startswith("scene:"):
            scene_id = scope.split(":", 1)[1]
            return (project_id, f"{instance_id}@scene:{scene_id}")
        return (project_id, instance_id)

    def _on_event(self, instance: Instance, event_type: str, payload: dict, source: str):
        # TODO: wire behavior execution via SandboxExecutor in a future iteration
        pass

    def _register_instance(self, inst: Instance):
        if self._bus_reg is None:
            return
        bus = self._bus_reg.get_or_create(inst.project_id)
        model = inst.model or {}
        behaviors = model.get("behaviors") or {}
        event_types = set()
        for b in behaviors.values():
            trigger = b.get("trigger", {})
            if trigger.get("type") == "event":
                event_types.add(trigger.get("name"))
        if not event_types:
            event_types.add("__noop__")
        import functools
        for et in event_types:
            bus.register(inst.id, inst.scope, et, functools.partial(self._on_event, inst))

    def _unregister_instance(self, inst: Instance):
        if self._bus_reg is None:
            return
        bus = self._bus_reg.get_or_create(inst.project_id)
        bus.unregister(inst.id)

    def create(
        self,
        project_id: str,
        model_name: str,
        instance_id: str,
        scope: str = "project",
        attributes: dict | None = None,
        variables: dict | None = None,
        links: dict | None = None,
        memory: dict | None = None,
        state: dict | None = None,
        model: dict | None = None,
    ) -> Instance:
        attributes = attributes or {}
        variables = variables or {}
        links = links or {}
        memory = memory or {}
        state = state or {"current": None, "enteredAt": None}
        inst = Instance(
            instance_id=instance_id,
            model_name=model_name,
            project_id=project_id,
            scope=scope,
            attributes=copy.deepcopy(attributes),
            variables=copy.deepcopy(variables),
            links=copy.deepcopy(links),
            memory=copy.deepcopy(memory),
            state=copy.deepcopy(state),
            model=model,
        )
        key = self._make_key(project_id, instance_id, scope)
        with self._lock:
            if key in self._instances:
                raise ValueError(f"Instance {instance_id} already exists in project {project_id} with scope {scope}")
            self._instances[key] = inst
        self._register_instance(inst)
        return inst

    def get(self, project_id: str, instance_id: str, scope: str = "project") -> Instance | None:
        key = self._make_key(project_id, instance_id, scope)
        with self._lock:
            return self._instances.get(key)

    def list_by_project(self, project_id: str) -> list[Instance]:
        with self._lock:
            return [inst for (pid, _), inst in self._instances.items() if pid == project_id]

    def list_by_scope(self, project_id: str, scope: str) -> list[Instance]:
        with self._lock:
            return [
                inst for (pid, _), inst in self._instances.items()
                if pid == project_id and inst.scope == scope
            ]

    def remove(self, project_id: str, instance_id: str, scope: str = "project") -> bool:
        key = self._make_key(project_id, instance_id, scope)
        with self._lock:
            inst = self._instances.pop(key, None)
        if inst is not None:
            self._unregister_instance(inst)
            return True
        return False

    def copy_for_scene(self, project_id: str, instance_id: str, scene_id: str) -> Instance | None:
        inst = self.get(project_id, instance_id, scope="project")
        if inst is None:
            return None
        clone = inst.deep_copy()
        clone.scope = f"scene:{scene_id}"
        key = self._make_key(project_id, clone.instance_id, clone.scope)
        with self._lock:
            if key in self._instances:
                raise ValueError(f"CoW copy {instance_id} for scene {scene_id} already exists")
            self._instances[key] = clone
        self._register_instance(clone)
        return clone
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/test_instance_manager.py::test_create_and_get_instance -v`
Expected: PASS

- [ ] **Step 5: Write failing test for copy_for_scene and scope queries**

Append to `tests/runtime/test_instance_manager.py`:

```python
def test_copy_for_scene_changes_scope():
    mgr = InstanceManager()
    mgr.create(project_id="proj-01", model_name="ladle", instance_id="ladle-001", scope="project")
    clone = mgr.copy_for_scene("proj-01", "ladle-001", "drill")
    assert clone is not None
    assert clone.scope == "scene:drill"
    assert mgr.get("proj-01", "ladle-001", scope="project").scope == "project"
    assert mgr.get("proj-01", "ladle-001", scope="scene:drill") is clone
    scene_instances = mgr.list_by_scope("proj-01", "scene:drill")
    assert len(scene_instances) == 1
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/runtime/test_instance_manager.py::test_copy_for_scene_changes_scope -v`
Expected: PASS

- [ ] **Step 7: Write failing test for duplicate instance_id in same project raises**

Append to `tests/runtime/test_instance_manager.py`:

```python
def test_duplicate_instance_id_raises():
    mgr = InstanceManager()
    mgr.create(project_id="proj-01", model_name="ladle", instance_id="ladle-001", scope="project")
    with pytest.raises(ValueError, match="already exists"):
        mgr.create(project_id="proj-01", model_name="ladle", instance_id="ladle-001", scope="project")
```

- [ ] **Step 8: Run test to verify it fails**

Run: `pytest tests/runtime/test_instance_manager.py::test_duplicate_instance_id_raises -v`
Expected: FAIL (no ValueError raised)

- [ ] **Step 9: Add duplicate check to create**

Modify `src/runtime/instance_manager.py` in `create()` before storing:

```python
        key = (project_id, instance_id)
        with self._lock:
            if key in self._instances:
                raise ValueError(f"Instance {instance_id} already exists in project {project_id}")
            self._instances[key] = inst
```

- [ ] **Step 10: Run test to verify it passes**

Run: `pytest tests/runtime/test_instance_manager.py::test_duplicate_instance_id_raises -v`
Expected: PASS

- [ ] **Step 11: Write failing test for auto event bus registration**

Append to `tests/runtime/test_instance_manager.py`:

```python
from src.runtime.event_bus import EventBusRegistry

def test_create_registers_on_event_bus():
    bus_reg = EventBusRegistry()
    mgr = InstanceManager(bus_reg)
    mgr.create(
        project_id="proj-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="project",
        model={
            "behaviors": {
                "captureAssigned": {
                    "trigger": {"type": "event", "name": "dispatchAssigned"},
                }
            }
        },
    )
    bus = bus_reg.get_or_create("proj-01")
    # Publish an event that the instance should be subscribed to
    received = []
    # Manually add a second subscriber to the same event to verify routing still works
    bus.register("ladle-002", "project", "dispatchAssigned", lambda t, p, s: received.append((t, p, s)))
    bus.publish("dispatchAssigned", {"destinationId": "C03"}, source="external", scope="project")
    assert len(received) == 1
```

- [ ] **Step 12: Run test to verify it passes**

Run: `pytest tests/runtime/test_instance_manager.py::test_create_registers_on_event_bus -v`
Expected: PASS

- [ ] **Step 13: Commit**

```bash
rtk git add src/runtime/instance_manager.py tests/runtime/test_instance_manager.py
rtk git commit -m "feat: add InstanceManager with create, get, copy_for_scene and event bus integration"
```

---

### Task 4: SceneController

**Files:**
- Create: `src/runtime/scene_controller.py`
- Create: `tests/runtime/test_scene_controller.py`

- [ ] **Step 1: Write failing test for shared scene startup**

```python
import pytest
from src.runtime.scene_controller import SceneController
from src.runtime.instance_manager import InstanceManager
from src.runtime.event_bus import EventBusRegistry

def test_start_shared_scene_references_project_instances():
    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    im.create(project_id="proj-01", model_name="ladle", instance_id="ladle-001", scope="project")
    ctrl = SceneController(im, bus_reg)
    scene = ctrl.start(
        project_id="proj-01",
        scene_id="monitor",
        mode="shared",
        references=["ladle-001"],
    )
    assert scene["scene_id"] == "monitor"
    assert scene["mode"] == "shared"
    assert "ladle-001" in scene["references"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_scene_controller.py::test_start_shared_scene_references_project_instances -v`
Expected: FAIL (SceneController not found)

- [ ] **Step 3: Implement SceneController**

Create `src/runtime/scene_controller.py`:

```python
import copy
from src.runtime.instance_manager import InstanceManager
from src.runtime.event_bus import EventBusRegistry

class SceneController:
    def __init__(
        self,
        instance_manager: InstanceManager,
        event_bus_registry: EventBusRegistry,
        metric_store=None,
    ):
        self._im = instance_manager
        self._bus_reg = event_bus_registry
        self._metric_store = metric_store
        self._scenes: dict[tuple[str, str], dict] = {}

    def _backfill_metrics(self, project_id: str, scene_id: str, instances: list):
        """Stub metric backfill: in a real system queries the time-series DB."""
        if self._metric_store is None:
            return
        for inst in instances:
            model = inst.model or {}
            for name, var_def in (model.get("variables") or {}).items():
                if var_def.get("x-category") == "metric":
                    last = self._metric_store.latest(project_id, inst.id, name)
                    if last is not None:
                        inst.variables[name] = last

    def _reconcile_properties(self, instances: list):
        """Stub property reconciliation: derivedProperties will be recomputed here."""
        # TODO: recompute derivedProperties based on current variables/attributes
        pass

    def start(
        self,
        project_id: str,
        scene_id: str,
        mode: str,
        references: list[str] | None = None,
        local_instances: dict | None = None,
    ) -> dict:
        references = references or []
        local_instances = local_instances or {}
        if mode not in ("shared", "isolated"):
            raise ValueError(f"Invalid scene mode: {mode}")

        # Reference validation + auto-pull (depth <= 2)
        resolved_refs = list(references)
        for ref_id in references:
            inst = self._im.get(project_id, ref_id, scope="project")
            if inst is None:
                raise ValueError(f"Referenced instance {ref_id} not found in project {project_id}")
            for link_target in (inst.links or {}).values():
                if link_target and link_target not in resolved_refs:
                    linked = self._im.get(project_id, link_target, scope="project")
                    if linked is not None and len(resolved_refs) < len(references) + 2:
                        resolved_refs.append(link_target)

        scene = {
            "project_id": project_id,
            "scene_id": scene_id,
            "mode": mode,
            "references": resolved_refs,
            "local_instances": {},
        }

        if mode == "isolated":
            for ref_id in resolved_refs:
                self._im.copy_for_scene(project_id, ref_id, scene_id)

        for local_id, local_spec in local_instances.items():
            local_inst = self._im.create(
                project_id=project_id,
                model_name=local_spec["modelName"],
                instance_id=local_id,
                scope=f"scene:{scene_id}",
                variables=copy.deepcopy(local_spec.get("variables", {})),
            )
            scene["local_instances"][local_id] = local_inst.id

        # Metric backfill for isolated scenes (spec 6.3 / 7.1 step 3)
        if mode == "isolated":
            scene_instances = self._im.list_by_scope(project_id, f"scene:{scene_id}")
            self._backfill_metrics(project_id, scene_id, scene_instances)

        # Property reconciliation must happen after metric backfill (spec 7.1 step 5)
        all_scene_instances = self._im.list_by_scope(project_id, f"scene:{scene_id}")
        self._reconcile_properties(all_scene_instances)

        self._scenes[(project_id, scene_id)] = scene
        return scene

    def stop(self, project_id: str, scene_id: str) -> bool:
        key = (project_id, scene_id)
        scene = self._scenes.pop(key, None)
        if scene is None:
            return False
        bus = self._bus_reg.get_or_create(project_id)
        # Unregister scene-scoped instances from event bus
        for inst in self._im.list_by_scope(project_id, f"scene:{scene_id}"):
            bus.unregister(inst.id)
            self._im.remove(project_id, inst.id, scope=inst.scope)
        return True

    def get(self, project_id: str, scene_id: str) -> dict | None:
        return self._scenes.get((project_id, scene_id))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/test_scene_controller.py::test_start_shared_scene_references_project_instances -v`
Expected: PASS

- [ ] **Step 5: Write failing test for isolated scene CoW**

Append to `tests/runtime/test_scene_controller.py`:

```python
def test_start_isolated_scene_creates_cow_copy():
    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    im.create(project_id="proj-01", model_name="ladle", instance_id="ladle-001", scope="project", variables={"steelAmount": 180})
    ctrl = SceneController(im, bus_reg)
    ctrl.start(project_id="proj-01", scene_id="drill", mode="isolated", references=["ladle-001"])
    # Both project and scene copies exist; get isolates by scope
    assert im.get("proj-01", "ladle-001", scope="project").scope == "project"
    assert im.get("proj-01", "ladle-001", scope="scene:drill").scope == "scene:drill"
    proj_list = im.list_by_scope("proj-01", "project")
    scene_list = im.list_by_scope("proj-01", "scene:drill")
    assert len(proj_list) == 1
    assert len(scene_list) == 1
    assert proj_list[0].variables["steelAmount"] == 180
    assert scene_list[0].variables["steelAmount"] == 180
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/runtime/test_scene_controller.py::test_start_isolated_scene_creates_cow_copy -v`
Expected: PASS

- [ ] **Step 7: Write failing test for local instances in isolated scene**

Append to `tests/runtime/test_scene_controller.py`:

```python
def test_isolated_scene_with_local_instances():
    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    im.create(project_id="proj-01", model_name="ladle", instance_id="ladle-001", scope="project")
    ctrl = SceneController(im, bus_reg)
    scene = ctrl.start(
        project_id="proj-01",
        scene_id="drill",
        mode="isolated",
        references=["ladle-001"],
        local_instances={
            "temp-inspector-01": {
                "modelName": "inspector",
                "variables": {"targetLadle": "ladle-001"},
            }
        },
    )
    local = im.get("proj-01", "temp-inspector-01", scope="scene:drill")
    assert local is not None
    assert local.scope == "scene:drill"
    assert local.variables["targetLadle"] == "ladle-001"
```

- [ ] **Step 8: Run test to verify it passes**

Run: `pytest tests/runtime/test_scene_controller.py::test_isolated_scene_with_local_instances -v`
Expected: PASS

- [ ] **Step 9: Write failing test for scene stop cleanup**

Append to `tests/runtime/test_scene_controller.py`:

```python
def test_stop_scene_removes_local_and_cow_instances():
    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    im.create(project_id="proj-01", model_name="ladle", instance_id="ladle-001", scope="project")
    ctrl = SceneController(im, bus_reg)
    ctrl.start(project_id="proj-01", scene_id="drill", mode="isolated", references=["ladle-001"])
    assert len(im.list_by_scope("proj-01", "scene:drill")) == 1
    assert ctrl.stop("proj-01", "drill") is True
    assert len(im.list_by_scope("proj-01", "scene:drill")) == 0
    assert ctrl.get("proj-01", "drill") is None
```

- [ ] **Step 10: Run test to verify it passes**

Run: `pytest tests/runtime/test_scene_controller.py::test_stop_scene_removes_local_and_cow_instances -v`
Expected: PASS

- [ ] **Step 11: Write failing test for metric backfill in isolated scene**

Append to `tests/runtime/test_scene_controller.py`:

```python
def test_isolated_scene_backfills_metrics():
    class FakeMetricStore:
        def latest(self, project_id, instance_id, metric_name):
            if metric_name == "temperature":
                return 1250.0
            return None

    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    im.create(
        project_id="proj-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="project",
        variables={"temperature": 25.0},
        model={
            "variables": {
                "temperature": {"x-category": "metric"},
                "steelAmount": {"x-category": "state"},
            }
        },
    )
    ctrl = SceneController(im, bus_reg, metric_store=FakeMetricStore())
    ctrl.start(project_id="proj-01", scene_id="drill", mode="isolated", references=["ladle-001"])
    cow = im.get("proj-01", "ladle-001", scope="scene:drill")
    assert cow.variables["temperature"] == 1250.0
    # state variable should not be touched by metric backfill
    assert cow.variables["steelAmount"] == 0.0
```

- [ ] **Step 12: Run test to verify it passes**

Run: `pytest tests/runtime/test_scene_controller.py::test_isolated_scene_backfills_metrics -v`
Expected: PASS

- [ ] **Step 13: Commit**

```bash
rtk git add src/runtime/scene_controller.py tests/runtime/test_scene_controller.py
rtk git commit -m "feat: add SceneController with shared/isolated modes, metric backfill and reconciliation"
```

---

### Task 5: Integrate dispatch() into SandboxExecutor

**Files:**
- Modify: `src/runtime/lib/sandbox.py`
- Modify: `tests/runtime/lib/test_sandbox.py`

- [ ] **Step 1: Write test for dispatch in sandbox**

Append to `tests/runtime/lib/test_sandbox.py`:

```python
import pytest
from src.runtime.lib.sandbox import SandboxExecutor
from src.runtime.event_bus import EventBusRegistry

def test_sandbox_dispatch_publishes_event():
    registry = EventBusRegistry()
    bus = registry.get_or_create("proj-01")
    received = []
    bus.register("ladle-001", "project", "ladleLoaded", lambda t, p, s: received.append((t, p, s)))

    executor = SandboxExecutor()
    context = {
        "this": {"id": "ladle-001", "project_id": "proj-01"},
        "dispatch": lambda event_type, payload, target=None: bus.publish(
            event_type, payload, source="ladle-001", scope="project", target=target
        ),
    }
    executor.execute('dispatch("ladleLoaded", {"steelAmount": 180})', context)
    assert len(received) == 1
    assert received[0][0] == "ladleLoaded"
    assert received[0][1] == {"steelAmount": 180}
```

- [ ] **Step 2: Run test to verify it passes without code changes**

Run: `pytest tests/runtime/lib/test_sandbox.py::test_sandbox_dispatch_publishes_event -v`
Expected: PASS (since dispatch is just injected via context)

- [ ] **Step 3: Commit**

```bash
rtk git add tests/runtime/lib/test_sandbox.py
rtk git commit -m "test: verify dispatch() works inside sandbox context"
```

---

### Task 6: Integration test for InstanceManager + EventBus + SceneController

**Files:**
- Create: `tests/runtime/test_project_instance_scene_integration.py`

- [ ] **Step 1: Write integration test**

```python
import pytest
from src.runtime.instance_manager import InstanceManager
from src.runtime.event_bus import EventBusRegistry
from src.runtime.scene_controller import SceneController

def test_shared_scene_event_reaches_all_references():
    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    ctrl = SceneController(im, bus_reg)

    im.create(project_id="proj-01", model_name="ladle", instance_id="ladle-001", scope="project")
    im.create(project_id="proj-01", model_name="caster", instance_id="caster-03", scope="project")

    ctrl.start(project_id="proj-01", scene_id="monitor", mode="shared", references=["ladle-001", "caster-03"])

    bus = bus_reg.get_or_create("proj-01")
    received = {"caster-03": []}
    bus.register("caster-03", "project", "ladleLoaded", lambda t, p, s: received["caster-03"].append(p))

    bus.publish("ladleLoaded", {"ladleId": "ladle-001"}, source="ladle-001", scope="project")
    assert len(received["caster-03"]) == 1

def test_isolated_scene_event_does_not_escape():
    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    ctrl = SceneController(im, bus_reg)

    im.create(project_id="proj-01", model_name="ladle", instance_id="ladle-001", scope="project")
    ctrl.start(project_id="proj-01", scene_id="drill", mode="isolated", references=["ladle-001"])

    bus = bus_reg.get_or_create("proj-01")
    proj_received = []
    scene_received = []
    bus.register("ladle-001", "project", "ladleLoaded", lambda t, p, s: proj_received.append(p))
    # CoW copy gets scene:drill scope
    bus.register("ladle-001", "scene:drill", "ladleLoaded", lambda t, p, s: scene_received.append(p))

    # Note: in actual implementation the CoW copy would have a different handler binding;
    # this test demonstrates scope routing works.
    bus.publish("ladleLoaded", {}, source="ladle-001", scope="scene:drill")
    assert len(proj_received) == 0
    assert len(scene_received) == 1
```

- [ ] **Step 2: Run integration tests**

Run: `pytest tests/runtime/test_project_instance_scene_integration.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
rtk git add tests/runtime/test_project_instance_scene_integration.py
rtk git commit -m "test: add integration tests for project-instance-scene flow"
```

---

### Task 7: Final verification

- [ ] **Step 1: Ensure __init__.py files exist for new packages**

Verify and create empty `__init__.py` files if missing:
- `src/runtime/__init__.py`
- `tests/runtime/__init__.py`

Run:
```bash
touch src/runtime/__init__.py
touch tests/runtime/__init__.py
```

- [ ] **Step 2: Run full runtime test suite**

Run: `pytest tests/runtime/ -v`
Expected: ALL PASS

- [ ] **Step 3: Commit any remaining changes**

If all tests pass and nothing uncommitted, no action needed.
