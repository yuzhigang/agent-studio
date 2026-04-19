# AlarmManager Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build AlarmManager that manages alarm lifecycle (inactive -> active -> inactive), reuses TriggerRegistry for trigger/clear evaluation, and supports silenceInterval de-duplication.

**Architecture:** AlarmManager is a standalone runtime component that registers trigger/clear callbacks via TriggerRegistry. Each alarm has AlarmState (inactive/active). SilenceInterval prevents re-notification while active. Message templates are interpolated at notification time. Events alarmTriggered/alarmCleared are published on the event bus.

**Tech Stack:** Python 3.12, pytest, existing TriggerRegistry / EventBus / InstanceManager infrastructure.

---

## File Structure

| File | Purpose |
|------|---------|
| `src/runtime/alarm_manager.py` (new) | AlarmManager core: AlarmState dataclass, register/unregister, trigger/clear callbacks, silence, message interpolation, event publishing |
| `tests/runtime/test_alarm_manager.py` (new) | Unit tests for AlarmManager logic |
| `tests/runtime/test_alarm_integration.py` (new) | Integration tests: alarm through demo-world instance |
| `src/runtime/world_registry.py` (modify) | Create AlarmManager after TriggerRegistry, add to bundle |
| `src/runtime/instance_manager.py` (modify) | Hook create/get/remove to register/unregister alarms |
| `worlds/demo-world/agents/logistics/heartbeat/model/index.yaml` (modify) | Add alarms section with overheat.warning example |

---

### Task 1: AlarmManager Skeleton + AlarmState

**Files:**
- Create: `src/runtime/alarm_manager.py`
- Test: `tests/runtime/test_alarm_manager.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from src.runtime.alarm_manager import AlarmManager, AlarmState


class FakeInstance:
    def __init__(self):
        self.instance_id = "inst-01"
        self.world_id = "demo-world"
        self.id = "inst-01"


def test_alarm_state_dataclass():
    state = AlarmState(alarm_id="a1", instance_id="inst-01", world_id="demo-world")
    assert state.state == "inactive"
    assert state.triggered_at is None
    assert state.cleared_at is None
    assert state.trigger_count == 0
    assert state.silence_expires_at is None


def test_alarm_manager_init():
    am = AlarmManager(trigger_registry=None, event_bus=None, store=None)
    assert am is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_alarm_manager.py::test_alarm_state_dataclass -v`
Expected: FAIL with "module not found"

- [ ] **Step 3: Write minimal implementation**

Create `src/runtime/alarm_manager.py`:

```python
from dataclasses import dataclass, field


@dataclass
class AlarmState:
    alarm_id: str
    instance_id: str
    world_id: str
    state: str = field(default="inactive")
    triggered_at: str | None = field(default=None)
    cleared_at: str | None = field(default=None)
    trigger_count: int = field(default=0)
    silence_expires_at: str | None = field(default=None)


class AlarmManager:
    def __init__(self, trigger_registry, event_bus, store=None):
        self._trigger_registry = trigger_registry
        self._event_bus = event_bus
        self._store = store
        self._states: dict[tuple[str, str, str], AlarmState] = {}
        self._trigger_ids: dict[tuple[str, str, str], list[str]] = {}

    def _key(self, instance, alarm_id: str):
        return (instance.world_id, instance.instance_id, alarm_id)

    def _get_state(self, instance, alarm_id: str) -> AlarmState:
        key = self._key(instance, alarm_id)
        if key not in self._states:
            self._states[key] = AlarmState(
                alarm_id=alarm_id,
                instance_id=instance.instance_id,
                world_id=instance.world_id,
            )
        return self._states[key]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/test_alarm_manager.py -v`
Expected: 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/runtime/alarm_manager.py tests/runtime/test_alarm_manager.py
git commit -m "feat: add AlarmManager skeleton and AlarmState dataclass"
```

---

### Task 2: Default Clear Logic + Register Alarms to TriggerRegistry

**Files:**
- Modify: `src/runtime/alarm_manager.py`
- Test: `tests/runtime/test_alarm_manager.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/runtime/test_alarm_manager.py`:

```python
def test_build_default_clear_for_condition():
    am = AlarmManager(None, None, None)
    trigger = {"type": "condition", "condition": "this.variables.temperature > 80"}
    clear = am._build_default_clear(trigger)
    assert clear["type"] == "condition"
    assert "not (this.variables.temperature > 80)" in clear["condition"]


def test_build_default_clear_for_event_is_none():
    am = AlarmManager(None, None, None)
    trigger = {"type": "event", "name": "start"}
    assert am._build_default_clear(trigger) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_alarm_manager.py::test_build_default_clear_for_condition -v`
Expected: FAIL with "method not found"

- [ ] **Step 3: Write minimal implementation**

Add to `src/runtime/alarm_manager.py` after AlarmManager class init:

```python
    @staticmethod
    def _build_default_clear(trigger_cfg: dict) -> dict | None:
        if trigger_cfg.get("type") == "condition" and "condition" in trigger_cfg:
            return {
                "type": "condition",
                "condition": f"not ({trigger_cfg['condition']})",
            }
        return None

    def register_instance_alarms(self, instance, alarm_configs: dict) -> None:
        for alarm_id, config in alarm_configs.items():
            trigger_cfg = config["trigger"]
            clear_cfg = config.get("clear") or self._build_default_clear(trigger_cfg)

            ids = []
            tids = self._trigger_registry.register(
                instance, trigger_cfg,
                callback=lambda inst, alarm_id=alarm_id, cfg=config: self._on_trigger(inst, alarm_id, cfg),
                tag=f"alarm:{alarm_id}:trigger",
            )
            ids.append(tids)

            if clear_cfg:
                cids = self._trigger_registry.register(
                    instance, clear_cfg,
                    callback=lambda inst, alarm_id=alarm_id, cfg=config: self._on_clear(inst, alarm_id, cfg),
                    tag=f"alarm:{alarm_id}:clear",
                )
                ids.append(cids)

            self._trigger_ids[self._key(instance, alarm_id)] = ids

    def unregister_instance_alarms(self, instance) -> None:
        keys_to_remove = [k for k in self._trigger_ids if k[0] == instance.world_id and k[1] == instance.instance_id]
        for key in keys_to_remove:
            for trigger_id in self._trigger_ids.pop(key, []):
                self._trigger_registry.unregister(trigger_id)
            self._states.pop(key, None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/test_alarm_manager.py::test_build_default_clear -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/runtime/alarm_manager.py tests/runtime/test_alarm_manager.py
git commit -m "feat: add default clear logic and alarm registration to TriggerRegistry"
```

---

### Task 3: _on_trigger and _on_clear Callbacks

**Files:**
- Modify: `src/runtime/alarm_manager.py`
- Test: `tests/runtime/test_alarm_manager.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/runtime/test_alarm_manager.py`:

```python
def test_on_trigger_inactive_to_active():
    am = AlarmManager(None, None, None)
    inst = FakeInstance()
    am._states[("demo-world", "inst-01", "a1")] = AlarmState(
        alarm_id="a1", instance_id="inst-01", world_id="demo-world", state="inactive"
    )
    am._on_trigger(inst, "a1", {"severity": "warning", "triggerMessage": "hot"})
    state = am._states[("demo-world", "inst-01", "a1")]
    assert state.state == "active"
    assert state.triggered_at is not None
    assert state.trigger_count == 1


def test_on_clear_active_to_inactive():
    am = AlarmManager(None, None, None)
    inst = FakeInstance()
    am._states[("demo-world", "inst-01", "a1")] = AlarmState(
        alarm_id="a1", instance_id="inst-01", world_id="demo-world",
        state="active", triggered_at="2026-01-01T00:00:00Z"
    )
    am._on_clear(inst, "a1", {"severity": "warning", "clearMessage": "ok"})
    state = am._states[("demo-world", "inst-01", "a1")]
    assert state.state == "inactive"
    assert state.cleared_at is not None


def test_on_trigger_already_active_increments_count():
    am = AlarmManager(None, None, None)
    inst = FakeInstance()
    am._states[("demo-world", "inst-01", "a1")] = AlarmState(
        alarm_id="a1", instance_id="inst-01", world_id="demo-world",
        state="active", triggered_at="2026-01-01T00:00:00Z", trigger_count=1
    )
    am._on_trigger(inst, "a1", {"severity": "warning"})
    state = am._states[("demo-world", "inst-01", "a1")]
    assert state.state == "active"
    assert state.trigger_count == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_alarm_manager.py::test_on_trigger_inactive_to_active -v`
Expected: FAIL with "method not found"

- [ ] **Step 3: Write minimal implementation**

Add to `src/runtime/alarm_manager.py`:

```python
    def _on_trigger(self, instance, alarm_id: str, config: dict) -> None:
        state = self._get_state(instance, alarm_id)
        if state.state == "active":
            state.trigger_count += 1
        else:
            state.state = "active"
            state.triggered_at = self._now()
            state.trigger_count = 1
            state.cleared_at = None

    def _on_clear(self, instance, alarm_id: str, config: dict) -> None:
        state = self._get_state(instance, alarm_id)
        if state.state != "active":
            return
        state.state = "inactive"
        state.cleared_at = self._now()
        state.silence_expires_at = None

    @staticmethod
    def _now() -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/test_alarm_manager.py::test_on_trigger -v`
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/runtime/alarm_manager.py tests/runtime/test_alarm_manager.py
git commit -m "feat: add alarm trigger and clear callbacks"
```

---

### Task 4: SilenceInterval Mechanism

**Files:**
- Modify: `src/runtime/alarm_manager.py`
- Test: `tests/runtime/test_alarm_manager.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/runtime/test_alarm_manager.py`:

```python
def test_silence_interval_blocks_retrigger():
    am = AlarmManager(None, None, None)
    inst = FakeInstance()
    config = {"severity": "warning", "silenceInterval": 60}

    # First trigger
    am._on_trigger(inst, "a1", config)
    state = am._get_state(inst, "a1")
    assert state.state == "active"
    assert state.trigger_count == 1
    assert state.silence_expires_at is not None

    # Second trigger during silence - should be ignored
    am._on_trigger(inst, "a1", config)
    assert state.trigger_count == 1  # unchanged


def test_silence_expired_allows_retrigger():
    am = AlarmManager(None, None, None)
    inst = FakeInstance()
    config = {"severity": "warning", "silenceInterval": 0}

    am._on_trigger(inst, "a1", config)
    state = am._get_state(inst, "a1")
    assert state.trigger_count == 1

    am._on_trigger(inst, "a1", config)
    assert state.trigger_count == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_alarm_manager.py::test_silence_interval_blocks_retrigger -v`
Expected: FAIL with "silence not implemented"

- [ ] **Step 3: Write minimal implementation**

Update `_on_trigger` in `src/runtime/alarm_manager.py`:

```python
    def _on_trigger(self, instance, alarm_id: str, config: dict) -> None:
        state = self._get_state(instance, alarm_id)
        if state.state == "active":
            if self._is_in_silence(state):
                return
            state.trigger_count += 1
        else:
            state.state = "active"
            state.triggered_at = self._now()
            state.trigger_count = 1
            state.cleared_at = None

        silence_seconds = config.get("silenceInterval", 0)
        if silence_seconds > 0:
            state.silence_expires_at = self._now_offset(silence_seconds)

    def _is_in_silence(self, state: AlarmState) -> bool:
        if state.silence_expires_at is None:
            return False
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        expires = datetime.fromisoformat(state.silence_expires_at)
        return now < expires

    @staticmethod
    def _now_offset(seconds: int) -> str:
        from datetime import datetime, timezone, timedelta
        return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/test_alarm_manager.py::test_silence -v`
Expected: 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/runtime/alarm_manager.py tests/runtime/test_alarm_manager.py
git commit -m "feat: add silenceInterval de-duplication for active alarms"
```

---

### Task 5: Message Template Interpolation + Event Publishing

**Files:**
- Modify: `src/runtime/alarm_manager.py`
- Test: `tests/runtime/test_alarm_manager.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/runtime/test_alarm_manager.py`:

```python
class FakeInstanceWithProps:
    def __init__(self):
        self.instance_id = "inst-01"
        self.world_id = "demo-world"
        self.id = "inst-01"
        self.variables = {"temperature": 85.0, "threshold": 80.0}
        self.attributes = {"unit": "celsius"}
        self.state = {"current": "monitoring"}


def test_interpolate_message():
    am = AlarmManager(None, None, None)
    inst = FakeInstanceWithProps()
    msg = am._interpolate_message("Temp {temperature} exceeds {threshold}", inst)
    assert msg == "Temp 85.0 exceeds 80.0"


def test_publish_alarm_triggered_event():
    events = []

    class FakeBus:
        def publish(self, event_type, payload, source=None, scope=None, target=None):
            events.append((event_type, payload))

    am = AlarmManager(None, FakeBus(), None)
    inst = FakeInstanceWithProps()
    config = {
        "category": "temp",
        "title": "Overheat",
        "severity": "warning",
        "level": 1,
        "triggerMessage": "Hot {temperature}",
    }
    am._on_trigger(inst, "a1", config)
    assert len(events) == 1
    etype, payload = events[0]
    assert etype == "alarmTriggered"
    assert payload["alarmId"] == "a1"
    assert payload["severity"] == "warning"
    assert "Hot 85.0" in payload["message"]
    assert payload["triggerCount"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_alarm_manager.py::test_interpolate_message -v`
Expected: FAIL with "method not found"

- [ ] **Step 3: Write minimal implementation**

Add to `src/runtime/alarm_manager.py`:

```python
    def _interpolate_message(self, template: str, instance) -> str:
        import re
        def replace(match):
            key = match.group(1)
            for section in ("variables", "attributes", "state"):
                src = getattr(instance, section, {})
                if isinstance(src, dict) and key in src:
                    return str(src[key])
            return match.group(0)
        return re.sub(r"\{(\w+)\}", replace, template)

    def _notify_trigger(self, state: AlarmState, config: dict, instance, repeated: bool = False) -> None:
        msg = self._interpolate_message(config.get("triggerMessage", ""), instance)
        payload = {
            "alarmId": state.alarm_id,
            "category": config.get("category", ""),
            "title": config.get("title", ""),
            "severity": config.get("severity", "info"),
            "level": config.get("level", 1),
            "message": msg,
            "instanceId": state.instance_id,
            "worldId": state.world_id,
            "timestamp": state.triggered_at,
            "triggerCount": state.trigger_count,
            "repeated": repeated,
        }
        if self._event_bus is not None:
            self._event_bus.publish("alarmTriggered", payload, source=state.instance_id, scope="world")

    def _notify_clear(self, state: AlarmState, config: dict, instance) -> None:
        msg = self._interpolate_message(config.get("clearMessage", ""), instance)
        payload = {
            "alarmId": state.alarm_id,
            "category": config.get("category", ""),
            "title": config.get("title", ""),
            "severity": config.get("severity", "info"),
            "level": config.get("level", 1),
            "message": msg,
            "instanceId": state.instance_id,
            "worldId": state.world_id,
            "timestamp": state.cleared_at,
        }
        if self._event_bus is not None:
            self._event_bus.publish("alarmCleared", payload, source=state.instance_id, scope="world")
```

Also update `_on_trigger` to call `_notify_trigger`:

```python
    def _on_trigger(self, instance, alarm_id: str, config: dict) -> None:
        state = self._get_state(instance, alarm_id)
        if state.state == "active":
            if self._is_in_silence(state):
                return
            state.trigger_count += 1
            self._notify_trigger(state, config, instance, repeated=True)
        else:
            state.state = "active"
            state.triggered_at = self._now()
            state.trigger_count = 1
            state.cleared_at = None
            self._notify_trigger(state, config, instance, repeated=False)

        silence_seconds = config.get("silenceInterval", 0)
        if silence_seconds > 0:
            state.silence_expires_at = self._now_offset(silence_seconds)
```

And update `_on_clear` to call `_notify_clear`:

```python
    def _on_clear(self, instance, alarm_id: str, config: dict) -> None:
        state = self._get_state(instance, alarm_id)
        if state.state != "active":
            return
        state.state = "inactive"
        state.cleared_at = self._now()
        state.silence_expires_at = None
        self._notify_clear(state, config, instance)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/test_alarm_manager.py -v`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/runtime/alarm_manager.py tests/runtime/test_alarm_manager.py
git commit -m "feat: add message interpolation and alarm event publishing"
```

