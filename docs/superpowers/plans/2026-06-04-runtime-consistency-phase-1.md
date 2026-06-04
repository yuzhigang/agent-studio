# Runtime Consistency Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make event subscription cleanup, checkpointing, SQLite persistence, and restart recovery deterministic and internally consistent.

**Architecture:** EventBus registrations receive opaque subscription IDs that are owned by EventTrigger entries. Checkpoint locking remains synchronous but async callers move it to a worker thread. World startup merges declared YAML with persisted snapshots before hydrating instances into memory without writing them back, while SQLite persists all runtime-owned fields including bindings.

**Tech Stack:** Python 3.11+, asyncio, threading, SQLite, PyYAML, pytest

---

## File Map

- Modify `src/runtime/event_bus.py`: assign and remove exact subscription IDs; constrain agent delivery to world-scope registrations.
- Modify `src/runtime/triggers/event_trigger.py`: retain and unregister EventBus subscription IDs.
- Modify `src/runtime/instance_manager.py`: stop ambiguous EventBus cleanup and add snapshot hydration without persistence.
- Modify `src/runtime/state_manager.py`: move auto-checkpoints to a worker thread and disable incomplete world event replay.
- Modify `src/runtime/stores/sqlite_store.py`: migrate, save, and load the bindings column.
- Modify `src/runtime/world_registry.py`: merge YAML declarations with snapshots before hydration.
- Modify focused runtime tests listed in each task.

### Task 1: Exact EventBus Subscription Ownership

**Files:**
- Modify: `src/runtime/event_bus.py`
- Modify: `src/runtime/triggers/event_trigger.py`
- Modify: `src/runtime/instance_manager.py`
- Test: `tests/runtime/test_event_bus.py`
- Test: `tests/runtime/test_world_instance_scene_integration.py`

- [ ] **Step 1: Write failing EventBus ownership and agent-scope tests**

Add tests that retain the returned IDs and prove exact removal:

```python
def test_unregister_removes_only_the_selected_subscription():
    bus = EventBus()
    world_hits = []
    scene_hits = []
    world_subscription = bus.register(
        "agent-1", "world", "tick", lambda *_: world_hits.append("world")
    )
    scene_subscription = bus.register(
        "agent-1", "scene:drill", "tick", lambda *_: scene_hits.append("scene")
    )

    assert world_subscription != scene_subscription
    bus.unregister(scene_subscription)
    bus.publish("tick", {}, "source", "world", "world-1")

    assert world_hits == ["world"]
    assert scene_hits == []


def test_agent_scope_does_not_reach_same_id_scene_subscription():
    bus = EventBus()
    world_hits = []
    scene_hits = []
    bus.register("agent-1", "world", "tick", lambda *_: world_hits.append("world"))
    bus.register("agent-1", "scene:drill", "tick", lambda *_: scene_hits.append("scene"))

    bus.publish("tick", {}, "source", "agent", "agent-1")

    assert world_hits == ["world"]
    assert scene_hits == []
```

Add an integration test using a model event behavior, an isolated scene copy,
and `SceneManager.stop()` to prove that the world instance still responds
after the scene trigger is removed.

- [ ] **Step 2: Run the new tests and verify failure**

Run:

```powershell
uv run --frozen pytest tests/runtime/test_event_bus.py tests/runtime/test_world_instance_scene_integration.py -q
```

Expected: failures show that `register()` returns `None`, unregistering a
same-ID scene registration removes both registrations, or agent routing reaches
the scene registration.

- [ ] **Step 3: Implement exact subscription IDs**

In `EventBus`, generate a UUID per registration, store subscriber tuples as
`(subscription_id, instance_id, scope, handler)`, return the ID, and make
`unregister(subscription_id)` remove only that tuple:

```python
subscription_id = str(uuid.uuid4())
self._subscribers.setdefault(event_type, []).append(
    (subscription_id, instance_id, scope, handler)
)
return subscription_id
```

Change agent matching to:

```python
if msg_scope == "agent":
    return inst_scope == "world" and instance_id == msg_target
```

Store `subscription_id` in `_HandlerInfo`, unregister that ID from
`EventTrigger.on_unregistered()`, and remove the direct
`bus.unregister(inst.id)` call from `InstanceManager._unregister_instance()`.
TriggerRegistry remains the owner of instance-trigger cleanup.

- [ ] **Step 4: Run focused tests**

Run:

```powershell
uv run --frozen pytest tests/runtime/test_event_bus.py tests/runtime/test_world_instance_scene_integration.py tests/runtime/test_instance_manager.py tests/runtime/test_trigger_registry.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit exact subscription changes**

```powershell
git add src/runtime/event_bus.py src/runtime/triggers/event_trigger.py src/runtime/instance_manager.py tests/runtime/test_event_bus.py tests/runtime/test_world_instance_scene_integration.py
git commit -m "fix: isolate event bus subscriptions"
```

### Task 2: Non-Blocking Automatic Checkpoints

**Files:**
- Modify: `src/runtime/state_manager.py`
- Test: `tests/runtime/test_state_manager.py`

- [ ] **Step 1: Write failing async checkpoint tests**

Add a test that starts the real auto-checkpoint loop with a tracked world,
replaces `asyncio.sleep` with a two-iteration controlled sleep, and wraps
`checkpoint_world` only to record completion after calling the real method:

```python
@pytest.mark.anyio
async def test_auto_checkpoint_completes_without_reacquiring_world_lock(monkeypatch):
    calls = 0

    async def controlled_sleep(_seconds):
        nonlocal calls
        calls += 1
        if calls > 1:
            state_mgr._shutdown = True

    monkeypatch.setattr("src.runtime.state_manager.asyncio.sleep", controlled_sleep)
    state_mgr.track_world("world-01")

    await asyncio.wait_for(state_mgr._auto_checkpoint_loop(), timeout=0.5)

    assert "world-01" in state_mgr._instance_store.world_states
```

Add a second test that replaces `checkpoint_world` with a short blocking
function and proves a concurrent coroutine can run while the checkpoint is in
progress.

- [ ] **Step 2: Run the new tests and verify failure**

Run:

```powershell
uv run --frozen pytest tests/runtime/test_state_manager.py -q
```

Expected: the deadlock test times out or the event-loop progress assertion
fails.

- [ ] **Step 3: Move automatic checkpoints to worker threads**

Replace the auto-loop lock acquisition block with:

```python
try:
    await asyncio.to_thread(self.checkpoint_world, world_id)
except asyncio.CancelledError:
    raise
except Exception:
    logger.exception("Automatic checkpoint failed for world %s", world_id)
```

Add a module logger. Keep `checkpoint_world()` as the sole owner of the
per-world lock.

- [ ] **Step 4: Run focused tests**

Run:

```powershell
uv run --frozen pytest tests/runtime/test_state_manager.py tests/runtime/test_world_registry.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit checkpoint changes**

```powershell
git add src/runtime/state_manager.py tests/runtime/test_state_manager.py
git commit -m "fix: prevent automatic checkpoint deadlocks"
```

### Task 3: Persist Bindings in SQLite

**Files:**
- Modify: `src/runtime/stores/sqlite_store.py`
- Test: `tests/runtime/stores/test_sqlite_store.py`

- [ ] **Step 1: Write failing bindings persistence and migration tests**

Extend instance save/load coverage:

```python
snapshot = {
    "model_name": "ladle",
    "bindings": {"orders": {"dataset": "active-orders"}},
}
store.save_instance("world-01", "inst-1", "world", snapshot)
assert store.load_instance("world-01", "inst-1", "world")["bindings"] == snapshot["bindings"]
assert store.list_instances("world-01")[0]["bindings"] == snapshot["bindings"]
```

Add a migration test that creates an old-form `instances` table without
`bindings`, opens `SQLiteStore`, and asserts existing rows load with
`bindings == {}`.

- [ ] **Step 2: Run the new tests and verify failure**

Run:

```powershell
uv run --frozen pytest tests/runtime/stores/test_sqlite_store.py -q
```

Expected: bindings are absent from loaded snapshots and the migration
assertion fails.

- [ ] **Step 3: Implement the bindings schema migration and serialization**

Add `bindings TEXT NOT NULL DEFAULT '{}'` to new schemas and apply this
idempotent migration for existing databases:

```python
if "bindings" not in columns:
    self._conn.execute(
        "ALTER TABLE instances ADD COLUMN bindings TEXT NOT NULL DEFAULT '{}'"
    )
```

Include bindings in instance INSERT/UPDATE, SELECT, `load_instance()`, and
`list_instances()` using `json.dumps` and `json.loads`.

- [ ] **Step 4: Run focused tests**

Run:

```powershell
uv run --frozen pytest tests/runtime/stores/test_sqlite_store.py tests/runtime/test_instance_manager.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit bindings persistence**

```powershell
git add src/runtime/stores/sqlite_store.py tests/runtime/stores/test_sqlite_store.py
git commit -m "fix: persist instance bindings"
```

### Task 4: Snapshot-First World Recovery

**Files:**
- Modify: `src/runtime/instance_manager.py`
- Modify: `src/runtime/state_manager.py`
- Modify: `src/runtime/world_registry.py`
- Test: `tests/runtime/test_state_manager.py`
- Test: `tests/runtime/test_world_registry_instance_loading.py`

- [ ] **Step 1: Write failing restart merge and replay-disable tests**

Add a registry restart test that:

1. Declares an instance with model defaults, bindings, attributes, and links.
2. Loads the world, changes runtime `state`, `variables`, `bindings`, `memory`,
   `audit`, and `lifecycle_state`, then checkpoints and unloads it.
3. Updates YAML `modelId`, one explicit attribute, and one explicit link.
4. Reloads and asserts runtime-owned fields came from the snapshot, YAML
   identity/model came from the declaration, explicit YAML attribute/link
   values won, and non-overridden snapshot attribute/link values remained.

Add separate assertions that explicitly declared empty `attributes: {}` and
`links: {}` erase snapshot maps, while omitted fields preserve snapshot maps.

Change the StateManager restore test to use an event store whose
`replay_after()` raises if called:

```python
class ReplayMustNotRun:
    def replay_after(self, world_id, last_event_id):
        raise AssertionError("world startup must not replay the incomplete event log")
```

- [ ] **Step 2: Run the new tests and verify failure**

Run:

```powershell
uv run --frozen pytest tests/runtime/test_world_registry_instance_loading.py tests/runtime/test_state_manager.py -q
```

Expected: YAML declaration loading deletes or overwrites the snapshot, bindings
are not loaded from declarations, and `restore_world()` calls replay.

- [ ] **Step 3: Add non-persisting snapshot hydration**

Add `InstanceManager.hydrate(snapshot, model=None)` that constructs an
`Instance` from a fully merged snapshot, registers its behaviors and alarms,
and adds it to memory without calling `_save_to_store()`.

Use the same snapshot keys as `build_persist_dict()` plus:

```python
{
    "world_id": world_id,
    "instance_id": instance_id,
    "scope": "world",
}
```

Refactor `InstanceManager.get()` to call `hydrate()` after loading a snapshot
so snapshot construction has one implementation.

- [ ] **Step 4: Merge declarations and snapshots before registration**

In `WorldRegistry._load_instance_declarations()`, load the world-scope snapshot
directly from the instance store before creating an instance.

For no snapshot, call `im.create()` with full YAML defaults and declaration
bindings.

For a snapshot, build a merged snapshot with these rules:

```python
merged = {
    "world_id": world_id,
    "instance_id": instance_id,
    "scope": "world",
    "model_name": model_id,
    "agent_namespace": decl.get("_agent_namespace"),
    "model_version": None,
    "state": snapshot.get("state", initial_state),
    "variables": snapshot.get("variables", initial_variables),
    "bindings": snapshot.get("bindings", initial_bindings),
    "memory": snapshot.get("memory", initial_memory),
    "audit": snapshot.get("audit", default_audit),
    "lifecycle_state": snapshot.get("lifecycle_state", "active"),
}
```

For `attributes` and `links`:

- If the declaration key is omitted, use the snapshot map, falling back to
  model defaults when the snapshot key is absent.
- If the declaration value is `{}`, use `{}`.
- If the declaration contains values, copy the snapshot map and overlay only
  the explicitly declared values.

Call `im.hydrate(merged, model=model)`. Do not call `im.get()` or `im.remove()`
during declaration loading.

- [ ] **Step 5: Disable incomplete world event replay**

Remove snapshot hydration and event replay from
`StateManager.restore_world()`. Keep metric backfill and property
reconciliation for instances already hydrated by WorldRegistry.

- [ ] **Step 6: Run focused tests**

Run:

```powershell
uv run --frozen pytest tests/runtime/test_world_registry_instance_loading.py tests/runtime/test_state_manager.py tests/runtime/test_instance_manager.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit snapshot-first recovery**

```powershell
git add src/runtime/instance_manager.py src/runtime/state_manager.py src/runtime/world_registry.py tests/runtime/test_state_manager.py tests/runtime/test_world_registry_instance_loading.py
git commit -m "fix: restore declared instances from snapshots"
```

### Task 5: Phase 1 Integration Verification

**Files:**
- Modify only files required to correct regressions introduced by Tasks 1-4.

- [ ] **Step 1: Run all phase-1 focused tests**

Run:

```powershell
uv run --frozen pytest tests/runtime/test_event_bus.py tests/runtime/test_world_instance_scene_integration.py tests/runtime/test_state_manager.py tests/runtime/test_world_registry_instance_loading.py tests/runtime/stores/test_sqlite_store.py tests/runtime/test_instance_manager.py tests/runtime/test_trigger_registry.py tests/runtime/test_world_registry.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run the full test suite**

Run:

```powershell
uv run --frozen pytest -q
```

Expected: no new failures compared with the documented baseline. If collection
still fails because the frozen lock omits runtime dependencies, record that
exact failure and run the widest available focused suite without modifying the
dependency lock.

- [ ] **Step 3: Check code and worktree boundaries**

Run:

```powershell
git diff --check
git status --short
```

Expected: `git diff --check` produces no output; unrelated pre-existing
worktree changes remain untouched.

- [ ] **Step 4: Commit any integration-only correction**

Only when Step 1 or Step 2 required a phase-1 correction, stage each corrected
phase-1 file by its exact path and commit it with:

```powershell
git commit -m "test: complete runtime consistency coverage"
```
