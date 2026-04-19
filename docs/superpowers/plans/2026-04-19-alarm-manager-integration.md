# AlarmManager Runtime Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire AlarmManager into the runtime: create it in WorldRegistry, hook InstanceManager create/get/remove lifecycle, add demo alarms to heartbeat model, and verify end-to-end with integration tests.

**Architecture:** AlarmManager is instantiated after TriggerRegistry in WorldRegistry.load_world(). InstanceManager calls alarm_manager.register_instance_alarms() after instance creation/loading and unregister_instance_alarms() before removal. The demo heartbeat model gets an `overheat.warning` alarm that fires via ConditionTrigger when temperature exceeds threshold.

**Tech Stack:** Python 3.12, pytest, existing WorldRegistry / InstanceManager / TriggerRegistry / EventBus infrastructure.

**Prerequisite:** Plan A (`2026-04-19-alarm-manager-core.md`) must be completed first — this plan depends on `src/runtime/alarm_manager.py` existing.

---

## File Structure

| File | Purpose |
|------|---------|
| `src/runtime/world_registry.py` (modify) | Import AlarmManager, instantiate after TriggerRegistry, add to bundle |
| `src/runtime/instance_manager.py` (modify) | Hook create/get/remove to call alarm_manager register/unregister |
| `worlds/demo-world/agents/logistics/heartbeat/model/index.yaml` (modify) | Add `alarms` section with `overheat.warning` |
| `tests/runtime/test_alarm_integration.py` (new) | Integration test: load demo-world, trigger alarm via tick event, verify alarmTriggered event |

---

### Task 1: WorldRegistry Integration

**Files:**
- Modify: `src/runtime/world_registry.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/runtime/test_alarm_integration.py`:

```python
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.runtime.world_registry import WorldRegistry


def test_load_world_creates_alarm_manager():
    registry = WorldRegistry(base_dir="worlds", global_model_paths=["agents"])
    bundle = registry.load_world("demo-world")
    assert "alarm_manager" in bundle
    assert bundle["alarm_manager"] is not None
    registry.unload_world("demo-world")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_alarm_integration.py::test_load_world_creates_alarm_manager -v`
Expected: FAIL with "KeyError: alarm_manager"

- [ ] **Step 3: Write minimal implementation**

Add import at top of `src/runtime/world_registry.py`:

```python
from src.runtime.alarm_manager import AlarmManager
```

After `im._trigger_registry = trigger_registry` (line 108), add:

```python
            alarm_manager = AlarmManager(trigger_registry, bus, store)
            im._alarm_manager = alarm_manager
```

Add `"alarm_manager": alarm_manager` to the bundle dict (around line 143-156):

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
                "alarm_manager": alarm_manager,
                "_registry": self,
                "force_stop_on_shutdown": False,
            }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/test_alarm_integration.py::test_load_world_creates_alarm_manager -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/runtime/world_registry.py tests/runtime/test_alarm_integration.py
git commit -m "feat: wire AlarmManager into WorldRegistry bundle"
```

---

### Task 2: InstanceManager Integration

**Files:**
- Modify: `src/runtime/instance_manager.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/runtime/test_alarm_integration.py`:

```python
def test_instance_manager_calls_alarm_manager_on_create():
    from src.runtime.alarm_manager import AlarmManager
    from src.runtime.instance_manager import InstanceManager
    from src.runtime.trigger_registry import TriggerRegistry
    from src.runtime.triggers.event_trigger import EventTrigger
    from src.runtime.triggers.value_changed_trigger import ValueChangedTrigger
    from src.runtime.triggers.condition_trigger import ConditionTrigger
    from src.runtime.triggers.timer_trigger import TimerTrigger
    from src.runtime.event_bus import EventBusRegistry

    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    tr = TriggerRegistry()
    tr.add_trigger(EventTrigger(bus_reg))
    tr.add_trigger(ValueChangedTrigger())
    tr.add_trigger(ConditionTrigger(im._sandbox))
    tr.add_trigger(TimerTrigger())
    im._trigger_registry = tr

    alarm_mgr = AlarmManager(tr, bus_reg.get_or_create("w1"))
    im._alarm_manager = alarm_mgr

    model = {
        "alarms": {
            "testAlarm": {
                "category": "test",
                "title": "Test",
                "severity": "warning",
                "trigger": {"type": "event", "name": "test"},
            }
        }
    }
    inst = im.create("w1", "m1", "i1", model=model)
    assert len(alarm_mgr._states) == 1

    im.remove("w1", "i1")
    assert len(alarm_mgr._states) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_alarm_integration.py::test_instance_manager_calls_alarm_manager_on_create -v`
Expected: FAIL with "no alarms registered" (InstanceManager does not call alarm_manager yet)

- [ ] **Step 3: Write minimal implementation**

In `src/runtime/instance_manager.py`, modify three methods.

After `self._save_to_store(inst)` in `create()` (around line 300), add:

```python
        if self._alarm_manager is not None and inst.model:
            alarm_configs = inst.model.get("alarms")
            if alarm_configs:
                self._alarm_manager.register_instance_alarms(inst, alarm_configs)
```

After `inst._update_snapshot()` and before `self._instances[key] = inst` in `get()` (around line 333-334), add:

```python
            if self._alarm_manager is not None and inst.model:
                alarm_configs = inst.model.get("alarms")
                if alarm_configs:
                    self._alarm_manager.register_instance_alarms(inst, alarm_configs)
```

In `remove()`, before `if inst is not None:` (around line 357), add:

```python
        if inst is not None and self._alarm_manager is not None:
            self._alarm_manager.unregister_instance_alarms(inst)
```

In `transition_lifecycle()`, before `if new_state == "archived":` (around line 371), add:

```python
        if inst is not None and self._alarm_manager is not None:
            self._alarm_manager.unregister_instance_alarms(inst)
```

Also add `_alarm_manager = None` to `__init__` defaults (it's already dynamically assigned, but ensure it works when None):

```python
    def __init__(...):
        ...
        self._alarm_manager = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/test_alarm_integration.py::test_instance_manager_calls_alarm_manager_on_create -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/runtime/instance_manager.py tests/runtime/test_alarm_integration.py
git commit -m "feat: hook InstanceManager lifecycle to AlarmManager"
```

---

### Task 3: Heartbeat Model Alarms

**Files:**
- Modify: `worlds/demo-world/agents/logistics/heartbeat/model/index.yaml`

- [ ] **Step 1: Add alarms section**

Append to `worlds/demo-world/agents/logistics/heartbeat/model/index.yaml` (after the `behaviors` section, before end of file):

```yaml
alarms:
  overheat.warning:
    category: overheat
    title: 传感器温度过高
    severity: warning
    level: 1
    silenceInterval: 30
    triggerMessage: "温度 {temperature}℃ 超过阈值 {threshold}℃"
    clearMessage: "温度已恢复正常"
    trigger:
      type: condition
      condition: "this.variables.temperature >= this.attributes.threshold"
    # clear omitted — defaults to "not (condition)"
```

- [ ] **Step 2: Verify YAML is valid**

Run: `python -c "import yaml; yaml.safe_load(open('worlds/demo-world/agents/logistics/heartbeat/model/index.yaml'))"`
Expected: no error

- [ ] **Step 3: Commit**

```bash
git add worlds/demo-world/agents/logistics/heartbeat/model/index.yaml
git commit -m "feat: add overheat.warning alarm to heartbeat model"
```

---

### Task 4: Integration Test — End-to-End Alarm Trigger

**Files:**
- Test: `tests/runtime/test_alarm_integration.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/runtime/test_alarm_integration.py`:

```python
import time


def test_alarm_triggered_via_condition():
    registry = WorldRegistry(base_dir="worlds", global_model_paths=["agents"])
    bundle = registry.load_world("demo-world")

    im = bundle["instance_manager"]
    bus = bundle["event_bus_registry"].get_or_create("demo-world")
    alarm_mgr = bundle["alarm_manager"]

    inst = im.get("demo-world", "sensor-01", scope="world")
    assert inst is not None

    # Start monitoring so condition trigger is relevant
    bus.publish("start", {}, source="test", scope="world")
    time.sleep(0.1)
    assert inst.state.get("current") == "monitoring"

    # Send temperature above threshold
    bus.publish("tick", {"temperature": 95.0}, source="test", scope="world")
    time.sleep(0.2)

    # Verify alarm is active
    state = alarm_mgr._get_state(inst, "overheat.warning")
    assert state.state == "active"
    assert state.trigger_count >= 1

    # Verify temperature updated
    assert inst.variables.get("temperature") == 95.0

    # Reset
    bus.publish("reset", {}, source="test", scope="world")
    time.sleep(0.1)

    # Alarm should be inactive after reset (temperature drops to 25, condition false)
    state = alarm_mgr._get_state(inst, "overheat.warning")
    assert state.state == "inactive"

    registry.unload_world("demo-world")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_alarm_integration.py::test_alarm_triggered_via_condition -v`
Expected: FAIL (alarm not triggered yet — may need to verify behavior works)

If it fails with "alarm not found", check that model loaded correctly. The alarm config is in the model YAML; model_loader should pick it up.

- [ ] **Step 3: Debug and fix if needed**

Common issues:
- Model loader may not include `alarms` key in loaded model. Check `src/runtime/model_loader.py` loads `alarms` from YAML.
- If alarms section is not loaded, add `"alarms"` to the model keys in model_loader.

In `src/runtime/model_loader.py`, around line 54-58, verify `alarms` is in the set of top-level keys:

```python
        top_level_keys = {
            "$schema", "metadata", "attributes", "variables", "derivedProperties",
            "links", "rules", "functions", "services", "states", "transitions",
            "behaviors", "events", "alarms", "schedules", "goals",
            "decisionPolicies", "memory", "plans",
        }
```

If `alarms` is missing, add it and commit:

```bash
git add src/runtime/model_loader.py
git commit -m "fix: include alarms in model_loader top-level keys"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/test_alarm_integration.py -v`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/runtime/test_alarm_integration.py
git commit -m "test: add alarm integration test via condition trigger"
```

---

## Spec Coverage Check

| Spec Requirement | Task |
|-----------------|------|
| AlarmManager created in WorldRegistry | Task 1 |
| InstanceManager hooks create/get/remove | Task 2 |
| Demo heartbeat model has alarms | Task 3 |
| End-to-end alarm trigger/clear verified | Task 4 |

No gaps.

## Placeholder Scan

- No "TBD", "TODO", "implement later"
- All test code is complete
- All implementation code is complete
- No "similar to Task N" references

## Type Consistency Check

- `AlarmManager.__init__` signature: `(trigger_registry, event_bus, store=None)` — consistent across plan A and plan B
- `register_instance_alarms(self, instance, alarm_configs)` — same in both plans
- `unregister_instance_alarms(self, instance)` — same in both plans
- `_alarm_manager` attribute on InstanceManager — dynamically assigned, initialized to None
