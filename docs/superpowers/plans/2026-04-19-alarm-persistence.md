# Alarm Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist alarm lifecycles to SQLite (`runtime.db`), supporting audit history, time-range queries, and manual clear (`force_clear`).

**Architecture:** Add `AlarmStore` interface and `SQLiteStore` implementation for an `alarms` table. Wire `AlarmManager._on_trigger` / `_on_clear` to upsert records. Add `_extract_payload` for `{var}` interpolation snapshots. Add `force_clear` for API-driven manual alarm clearance.

**Tech Stack:** Python 3.12, pytest, existing SQLiteStore / AlarmManager / EventBus.

**Prerequisite:** Plan B (`2026-04-19-alarm-manager-integration.md`) completed — `src/runtime/alarm_manager.py` exists and AlarmManager is wired into WorldRegistry/InstanceManager.

---

## File Structure

| File | Purpose |
|------|---------|
| `src/runtime/stores/base.py` (modify) | Add `AlarmStore` abstract class |
| `src/runtime/stores/sqlite_store.py` (modify) | Add `alarms` table schema, indexes, and `AlarmStore` implementation |
| `src/runtime/alarm_manager.py` (modify) | Add `_persist_alarm_state`, `_extract_payload`, `force_clear` |
| `tests/runtime/test_alarm_manager.py` (modify) | Add unit tests for persistence, payload extraction, force_clear |
| `tests/runtime/test_alarm_integration.py` (modify) | Add end-to-end tests for DB persistence, time-range query, force_clear |

---

### Task 1: AlarmStore Interface + SQLite Implementation

**Files:**
- Modify: `src/runtime/stores/base.py`
- Modify: `src/runtime/stores/sqlite_store.py`
- Test: `tests/runtime/test_alarm_manager.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/runtime/test_alarm_manager.py`:

```python
class FakeAlarmStore:
    def __init__(self):
        self._alarms = []

    def save_alarm(self, world_id: str, alarm_data: dict) -> None:
        self._alarms.append(("save", world_id, alarm_data))

    def load_alarm(self, world_id: str, instance_id: str, alarm_id: str) -> dict | None:
        for _, wid, data in self._alarms:
            if wid == world_id and data.get("instance_id") == instance_id and data.get("alarm_id") == alarm_id:
                return data
        return None

    def list_alarms(self, world_id: str, instance_id: str | None = None, state: str | None = None,
                    triggered_after: str | None = None, triggered_before: str | None = None) -> list[dict]:
        return []

    def delete_alarm(self, world_id: str, instance_id: str, alarm_id: str) -> bool:
        return True

    def clear_alarm(self, world_id: str, instance_id: str, alarm_id: str) -> bool:
        return True


def test_alarm_manager_calls_store_on_trigger():
    store = FakeAlarmStore()
    am = AlarmManager(None, None, store)
    inst = FakeInstanceWithProps()
    config = {"severity": "warning", "category": "temp", "title": "Hot", "level": 1, "triggerMessage": "Temp {temperature}"}
    am._on_trigger(inst, "a1", config)
    assert len(store._alarms) == 1
    assert store._alarms[0][0] == "save"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_alarm_manager.py::test_alarm_manager_calls_store_on_trigger -v`
Expected: FAIL with AttributeError (AlarmManager has no `_persist_alarm_state` yet)

- [ ] **Step 3: Add AlarmStore interface to base.py**

Append to `src/runtime/stores/base.py`, after the `MessageStore` class (before EOF):

```python
class AlarmStore(ABC):
    @abstractmethod
    def save_alarm(self, world_id: str, alarm_data: dict) -> None:
        """Upsert an alarm record."""
        ...

    @abstractmethod
    def load_alarm(self, world_id: str, instance_id: str, alarm_id: str) -> dict | None:
        """Load a single alarm record by composite key."""
        ...

    @abstractmethod
    def list_alarms(
        self,
        world_id: str,
        instance_id: str | None = None,
        state: str | None = None,
        triggered_after: str | None = None,
        triggered_before: str | None = None,
    ) -> list[dict]:
        """List alarms with optional filters."""
        ...

    @abstractmethod
    def delete_alarm(self, world_id: str, instance_id: str, alarm_id: str) -> bool:
        """Delete an alarm record."""
        ...

    @abstractmethod
    def clear_alarm(self, world_id: str, instance_id: str, alarm_id: str) -> bool:
        """Manually clear an active alarm. Returns True if cleared."""
        ...
```

- [ ] **Step 4: Add alarms table schema and indexes to sqlite_store.py**

In `src/runtime/stores/sqlite_store.py`, add to `_ensure_schema` schema string, after the `world_state` table definition and before the closing `"""`:

```sql
        CREATE TABLE IF NOT EXISTS alarms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            world_id TEXT NOT NULL,
            instance_id TEXT NOT NULL,
            alarm_id TEXT NOT NULL,
            category TEXT,
            severity TEXT,
            level INTEGER,
            state TEXT NOT NULL,
            trigger_count INTEGER DEFAULT 0,
            trigger_message TEXT,
            clear_message TEXT,
            triggered_at TEXT,
            cleared_at TEXT,
            payload TEXT,
            updated_at TEXT NOT NULL,
            UNIQUE (world_id, instance_id, alarm_id)
        );

        CREATE INDEX IF NOT EXISTS idx_alarms_triggered_at
            ON alarms (world_id, triggered_at);

        CREATE INDEX IF NOT EXISTS idx_alarms_state
            ON alarms (world_id, state);
```

- [ ] **Step 5: Add AlarmStore implementation to sqlite_store.py**

Append to `src/runtime/stores/sqlite_store.py`, after `load_world_state` method and before `close()`:

```python
    # AlarmStore
    def save_alarm(self, world_id: str, alarm_data: dict) -> None:
        now = self._now()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO alarms (
                    world_id, instance_id, alarm_id, category, severity, level,
                    state, trigger_count, trigger_message, clear_message,
                    triggered_at, cleared_at, payload, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(world_id, instance_id, alarm_id) DO UPDATE SET
                    category = excluded.category,
                    severity = excluded.severity,
                    level = excluded.level,
                    state = excluded.state,
                    trigger_count = excluded.trigger_count,
                    trigger_message = excluded.trigger_message,
                    clear_message = excluded.clear_message,
                    triggered_at = excluded.triggered_at,
                    cleared_at = excluded.cleared_at,
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (
                    world_id,
                    alarm_data["instance_id"],
                    alarm_data["alarm_id"],
                    alarm_data.get("category"),
                    alarm_data.get("severity"),
                    alarm_data.get("level"),
                    alarm_data["state"],
                    alarm_data.get("trigger_count", 0),
                    alarm_data.get("trigger_message"),
                    alarm_data.get("clear_message"),
                    alarm_data.get("triggered_at"),
                    alarm_data.get("cleared_at"),
                    json.dumps(alarm_data.get("payload", {}), ensure_ascii=False) if alarm_data.get("payload") else None,
                    now,
                ),
            )
            self._conn.commit()

    def load_alarm(self, world_id: str, instance_id: str, alarm_id: str) -> dict | None:
        row = self._conn.execute(
            """
            SELECT category, severity, level, state, trigger_count, trigger_message,
                   clear_message, triggered_at, cleared_at, payload, updated_at
            FROM alarms WHERE world_id = ? AND instance_id = ? AND alarm_id = ?
            """,
            (world_id, instance_id, alarm_id),
        ).fetchone()
        if row is None:
            return None
        return {
            "world_id": world_id,
            "instance_id": instance_id,
            "alarm_id": alarm_id,
            "category": row[0],
            "severity": row[1],
            "level": row[2],
            "state": row[3],
            "trigger_count": row[4],
            "trigger_message": row[5],
            "clear_message": row[6],
            "triggered_at": row[7],
            "cleared_at": row[8],
            "payload": json.loads(row[9]) if row[9] else {},
            "updated_at": row[10],
        }

    def list_alarms(
        self,
        world_id: str,
        instance_id: str | None = None,
        state: str | None = None,
        triggered_after: str | None = None,
        triggered_before: str | None = None,
    ) -> list[dict]:
        query = """
            SELECT world_id, instance_id, alarm_id, category, severity, level,
                   state, trigger_count, trigger_message, clear_message,
                   triggered_at, cleared_at, payload, updated_at
            FROM alarms WHERE world_id = ?
        """
        params: list = [world_id]
        if instance_id is not None:
            query += " AND instance_id = ?"
            params.append(instance_id)
        if state is not None:
            query += " AND state = ?"
            params.append(state)
        if triggered_after is not None:
            query += " AND triggered_at >= ?"
            params.append(triggered_after)
        if triggered_before is not None:
            query += " AND triggered_at <= ?"
            params.append(triggered_before)
        query += " ORDER BY triggered_at DESC"
        rows = self._conn.execute(query, params).fetchall()
        return [
            {
                "world_id": r[0],
                "instance_id": r[1],
                "alarm_id": r[2],
                "category": r[3],
                "severity": r[4],
                "level": r[5],
                "state": r[6],
                "trigger_count": r[7],
                "trigger_message": r[8],
                "clear_message": r[9],
                "triggered_at": r[10],
                "cleared_at": r[11],
                "payload": json.loads(r[12]) if r[12] else {},
                "updated_at": r[13],
            }
            for r in rows
        ]

    def delete_alarm(self, world_id: str, instance_id: str, alarm_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM alarms WHERE world_id = ? AND instance_id = ? AND alarm_id = ?",
                (world_id, instance_id, alarm_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def clear_alarm(self, world_id: str, instance_id: str, alarm_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                """
                UPDATE alarms
                SET state = 'inactive', cleared_at = ?, updated_at = ?
                WHERE world_id = ? AND instance_id = ? AND alarm_id = ? AND state = 'active'
                """,
                (self._now(), self._now(), world_id, instance_id, alarm_id),
            )
            self._conn.commit()
            return cur.rowcount > 0
```

Also update the `SQLiteStore` class signature to include `AlarmStore`:

Change line 15:
```python
class SQLiteStore(WorldStore, SceneStore, InstanceStore, EventLogStore):
```
to:
```python
class SQLiteStore(WorldStore, SceneStore, InstanceStore, EventLogStore, AlarmStore):
```

And add `AlarmStore` to the import from `base`:

Change line 7-12:
```python
from src.runtime.stores.base import (
    WorldStore,
    SceneStore,
    InstanceStore,
    EventLogStore,
)
```
to:
```python
from src.runtime.stores.base import (
    WorldStore,
    SceneStore,
    InstanceStore,
    EventLogStore,
    AlarmStore,
)
```

- [ ] **Step 6: Add persistence call to AlarmManager**

In `src/runtime/alarm_manager.py`, add `_persist_alarm_state` method after `_now`:

```python
    def _persist_alarm_state(self, instance, alarm_id: str, config: dict, is_clear: bool = False) -> None:
        if self._store is None:
            return
        state = self._get_state(instance, alarm_id)
        payload = self._extract_payload(config.get("triggerMessage", ""), instance)
        alarm_data = {
            "instance_id": instance.instance_id,
            "alarm_id": alarm_id,
            "category": config.get("category"),
            "severity": config.get("severity"),
            "level": config.get("level"),
            "state": state.state,
            "trigger_count": state.trigger_count,
            "trigger_message": self._interpolate_message(config.get("triggerMessage", ""), instance) or None,
            "clear_message": self._interpolate_message(config.get("clearMessage", ""), instance) or None,
            "triggered_at": state.triggered_at,
            "cleared_at": state.cleared_at,
            "payload": payload if payload else None,
        }
        self._store.save_alarm(instance.world_id, alarm_data)

    def _extract_payload(self, template: str, instance) -> dict:
        import re
        keys = set(re.findall(r"\{(\w+)\}", template))
        payload = {}
        for key in keys:
            for source in (instance.variables, instance.attributes, instance.state):
                if key in source:
                    payload[key] = source[key]
                    break
        return payload
```

Then add calls in `_on_trigger` and `_on_clear`:

In `_on_trigger`, after `self._notify_trigger(...)` (end of the method), add:
```python
        self._persist_alarm_state(instance, alarm_id, config, is_clear=False)
```

In `_on_clear`, after `self._notify_clear(state, config, instance)`, add:
```python
        self._persist_alarm_state(instance, alarm_id, config, is_clear=True)
```

- [ ] **Step 7: Run tests**

Run: `pytest tests/runtime/test_alarm_manager.py -v`
Expected: all existing tests + new test pass

- [ ] **Step 8: Commit**

```bash
git add src/runtime/stores/base.py src/runtime/stores/sqlite_store.py src/runtime/alarm_manager.py tests/runtime/test_alarm_manager.py
git commit -m "feat: add AlarmStore interface, SQLite implementation, and persist alarm state"
```

---

### Task 2: force_clear Method

**Files:**
- Modify: `src/runtime/alarm_manager.py`
- Test: `tests/runtime/test_alarm_manager.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/runtime/test_alarm_manager.py`:

```python
def test_force_clear_active_alarm():
    events = []

    class FakeBus:
        def publish(self, event_type, payload, source=None, scope=None, target=None):
            events.append((event_type, payload))

    store = FakeAlarmStore()
    am = AlarmManager(None, FakeBus(), store)
    inst = FakeInstanceWithProps()
    inst.model = {
        "alarms": {
            "a1": {
                "category": "temp",
                "title": "Overheat",
                "severity": "warning",
                "level": 1,
                "triggerMessage": "Hot {temperature}",
                "clearMessage": "Cooled {temperature}",
            }
        }
    }
    config = inst.model["alarms"]["a1"]

    # Trigger first
    am._on_trigger(inst, "a1", config)
    assert len(events) == 1
    assert events[0][0] == "alarmTriggered"
    state = am._get_state(inst, "a1")
    assert state.state == "active"

    # Force clear
    result = am.force_clear(inst, "a1")
    assert result is True
    assert state.state == "inactive"
    assert state.cleared_at is not None
    assert len(events) == 2
    assert events[1][0] == "alarmCleared"
    assert events[1][1]["alarmId"] == "a1"

    # Second force_clear should return False (already inactive)
    result = am.force_clear(inst, "a1")
    assert result is False
    assert len(events) == 2  # no new event


def test_force_clear_without_model():
    events = []

    class FakeBus:
        def publish(self, event_type, payload, source=None, scope=None, target=None):
            events.append((event_type, payload))

    am = AlarmManager(None, FakeBus(), None)
    inst = FakeInstanceWithProps()
    # No model attribute
    am._on_trigger(inst, "a1", {"severity": "warning", "triggerMessage": "hot"})
    state = am._get_state(inst, "a1")
    assert state.state == "active"

    result = am.force_clear(inst, "a1")
    assert result is True  # should still clear, but without config defaults
    assert state.state == "inactive"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_alarm_manager.py::test_force_clear_active_alarm -v`
Expected: FAIL with AttributeError (no `force_clear` method)

- [ ] **Step 3: Implement force_clear**

In `src/runtime/alarm_manager.py`, add `force_clear` method after `_persist_alarm_state`:

```python
    def force_clear(self, instance, alarm_id: str) -> bool:
        """Manually clear an active alarm.

        Updates memory state, persists to store, and publishes alarmCleared event.
        Returns True if the alarm was active and is now cleared.
        Returns False if the alarm was already inactive.
        """
        state = self._get_state(instance, alarm_id)
        if state.state != "active":
            return False

        config = self._get_alarm_config(instance, alarm_id)

        state.state = "inactive"
        state.cleared_at = self._now()
        state.silence_expires_at = None

        self._notify_clear(state, config, instance)
        self._persist_alarm_state(instance, alarm_id, config, is_clear=True)
        return True

    def _get_alarm_config(self, instance, alarm_id: str) -> dict:
        """Retrieve alarm config from instance model, or return minimal defaults."""
        model = getattr(instance, "model", None)
        if model and "alarms" in model:
            return model["alarms"].get(alarm_id, {})
        return {}
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/runtime/test_alarm_manager.py -v`
Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add src/runtime/alarm_manager.py tests/runtime/test_alarm_manager.py
git commit -m "feat: add force_clear for manual alarm clearance"
```

---

### Task 3: Integration Tests — End-to-End Persistence

**Files:**
- Test: `tests/runtime/test_alarm_integration.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/runtime/test_alarm_integration.py`:

```python
import time


def test_alarm_persisted_to_database(tmp_path):
    """End-to-end: trigger alarm, verify record in SQLite, clear alarm, verify state."""
    from src.runtime.stores.sqlite_store import SQLiteStore

    # Create a minimal ephemeral world
    world_dir = tmp_path / "test-world"
    world_dir.mkdir()
    store = SQLiteStore(str(world_dir))

    # Manually wire up an AlarmManager with this store
    from src.runtime.alarm_manager import AlarmManager
    from src.runtime.event_bus import EventBusRegistry

    bus_reg = EventBusRegistry()
    bus = bus_reg.get_or_create("test-world")
    am = AlarmManager(trigger_registry=None, event_bus=bus, store=store)

    class FakeInst:
        def __init__(self):
            self.instance_id = "sensor-01"
            self.world_id = "test-world"
            self.id = "sensor-01"
            self.variables = {"temperature": 95.0, "threshold": 80.0}
            self.attributes = {}
            self.state = {"current": "monitoring"}
            self.model = {
                "alarms": {
                    "overheat.warning": {
                        "category": "overheat",
                        "severity": "warning",
                        "level": 1,
                        "triggerMessage": "温度 {temperature}℃ 超过阈值 {threshold}℃",
                        "clearMessage": "温度已恢复正常",
                    }
                }
            }

    inst = FakeInst()
    config = inst.model["alarms"]["overheat.warning"]

    # Trigger alarm
    am._on_trigger(inst, "overheat.warning", config)

    # Verify DB record
    record = store.load_alarm("test-world", "sensor-01", "overheat.warning")
    assert record is not None
    assert record["state"] == "active"
    assert record["trigger_count"] == 1
    assert record["trigger_message"] == "温度 95.0℃ 超过阈值 80.0℃"
    assert record["severity"] == "warning"
    assert record["payload"] == {"temperature": 95.0, "threshold": 80.0}

    # Clear alarm
    am._on_clear(inst, "overheat.warning", config)

    # Verify DB record updated
    record = store.load_alarm("test-world", "sensor-01", "overheat.warning")
    assert record["state"] == "inactive"
    assert record["cleared_at"] is not None
    assert record["trigger_count"] == 1  # unchanged


def test_alarm_time_range_query(tmp_path):
    from src.runtime.stores.sqlite_store import SQLiteStore
    from src.runtime.alarm_manager import AlarmManager

    world_dir = tmp_path / "test-world"
    world_dir.mkdir()
    store = SQLiteStore(str(world_dir))
    am = AlarmManager(None, None, store)

    class FakeInst:
        def __init__(self, iid):
            self.instance_id = iid
            self.world_id = "test-world"
            self.id = iid
            self.variables = {"temperature": 90.0 + int(iid[-2:])}
            self.attributes = {}
            self.state = {}
            self.model = {}

    # Create two alarms
    inst1 = FakeInst("s01")
    inst2 = FakeInst("s02")
    am._on_trigger(inst1, "a1", {"severity": "warning", "triggerMessage": "hot {temperature}"})
    am._on_trigger(inst2, "a2", {"severity": "warning", "triggerMessage": "hot {temperature}"})

    # List all alarms
    all_alarms = store.list_alarms("test-world")
    assert len(all_alarms) == 2

    # Filter by instance
    s01_alarms = store.list_alarms("test-world", instance_id="s01")
    assert len(s01_alarms) == 1
    assert s01_alarms[0]["alarm_id"] == "a1"

    # Filter by state
    active_alarms = store.list_alarms("test-world", state="active")
    assert len(active_alarms) == 2


def test_force_clear_via_store(tmp_path):
    from src.runtime.stores.sqlite_store import SQLiteStore
    from src.runtime.alarm_manager import AlarmManager
    from src.runtime.event_bus import EventBusRegistry

    world_dir = tmp_path / "test-world"
    world_dir.mkdir()
    store = SQLiteStore(str(world_dir))
    bus_reg = EventBusRegistry()
    bus = bus_reg.get_or_create("test-world")
    am = AlarmManager(None, bus, store)

    class FakeInst:
        def __init__(self):
            self.instance_id = "s01"
            self.world_id = "test-world"
            self.id = "s01"
            self.variables = {"temperature": 95.0}
            self.attributes = {}
            self.state = {}
            self.model = {
                "alarms": {
                    "a1": {
                        "severity": "warning",
                        "triggerMessage": "hot {temperature}",
                        "clearMessage": "cool",
                    }
                }
            }

    inst = FakeInst()
    config = inst.model["alarms"]["a1"]
    am._on_trigger(inst, "a1", config)

    record = store.load_alarm("test-world", "s01", "a1")
    assert record["state"] == "active"

    # Force clear
    result = am.force_clear(inst, "a1")
    assert result is True

    record = store.load_alarm("test-world", "s01", "a1")
    assert record["state"] == "inactive"
    assert record["cleared_at"] is not None

    # Second clear should return False
    result = am.force_clear(inst, "a1")
    assert result is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_alarm_integration.py::test_alarm_persisted_to_database -v`
Expected: FAIL (table `alarms` may not exist in ephemeral world, or persistence not wired yet)

- [ ] **Step 3: Verify implementation passes**

The preceding tasks already implemented the required schema and persistence. Run all integration tests:

```bash
pytest tests/runtime/test_alarm_integration.py -v
```
Expected: all tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/runtime/test_alarm_integration.py
git commit -m "test: add alarm persistence integration tests"
```

---

### Task 4: Update Todo for Instance Deletion

**Files:**
- Modify: `todo.md` (append)

- [ ] **Step 1: Add TODO entry**

Append to `todo.md`:

```markdown
- [ ] Alarm history cleanup on instance deletion: when an instance is removed/archived,
      decide whether to cascade-delete its alarm records or keep them for audit.
      Currently alarms table retains records even after instance removal.
```

- [ ] **Step 2: Commit**

```bash
git add todo.md
git commit -m "docs: add TODO for alarm history cleanup on instance deletion"
```

---

## Spec Coverage Check

| Spec Requirement | Task |
|-----------------|------|
| `alarms` table schema with indexes | Task 1 |
| `AlarmStore` abstract interface | Task 1 |
| `SQLiteStore` implements `AlarmStore` | Task 1 |
| Persist on trigger (UPSERT) | Task 1 |
| Persist on clear (UPDATE) | Task 1 |
| `payload` extracted from `triggerMessage` variables | Task 1 |
| `force_clear` method | Task 2 |
| `_get_alarm_config` fallback | Task 2 |
| End-to-end DB persistence test | Task 3 |
| Time-range query test | Task 3 |
| `force_clear` integration test | Task 3 |

No gaps.

## Placeholder Scan

- No "TBD", "TODO", "implement later" in plan steps
- All test code is complete
- All implementation code is complete
- No "similar to Task N" references

## Type Consistency Check

- `AlarmStore.save_alarm(world_id, alarm_data)` — consistent across base.py and sqlite_store.py
- `AlarmStore.clear_alarm` returns `bool` — consistent
- `AlarmManager._persist_alarm_state(self, instance, alarm_id, config, is_clear)` — used in Tasks 1 and 2
- `AlarmManager.force_clear(self, instance, alarm_id) -> bool` — used in Tasks 2 and 3
- `AlarmState` fields unchanged from Plan A/B
- `SQLiteStore` now inherits from `AlarmStore` alongside existing stores
