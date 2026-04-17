# Code Review: MessageHub Worker-Level Refactor

**Branch:** `master`  
**Commit:** `73b3d169efe036f528c8b0762fb002012c19c37d`  
**Date:** 2026-04-17  
**Scope:** MessageHub refactor from per-project to worker-level singleton

---

## Summary

Found 7 issues in the recent changes. Several are functional bugs that will directly impact correctness in multi-project or production scenarios.

---

## Issues

### 1. `InboxProcessor._distribute` causes N^2 message duplication

**Description:** `_distribute` loops over each subscribed `project_id` and calls `self._hub.publish(...)`. However, `MessageHub.publish()` itself loops over all subscribed projects for that `event_type`. If N projects subscribe to the same external event, each project receives the message N times.

**Fix:** Call `event_bus.publish(...)` directly per project instead of re-entering the hub.

**Link:** [`src/runtime/inbox_processor.py#L53-L67`](https://github.com/yuzhigang/agent-studio/blob/73b3d169efe036f528c8b0762fb002012c19c37d/src/runtime/inbox_processor.py#L53-L67)

---

### 2. `ProjectRegistry.load_project` never populates `"model_events"`

**Description:** The bundle dict returned by `ProjectRegistry.load_project` does not include a `"model_events"` key. Both `run_command.py` and `run_inline.py` call `bundle.get("model_events", {})`, which always yields an empty dict. This leaves `MessageHub._subscriptions` empty and completely breaks external event routing through the hub.

**Fix:** Populate `model_events` in the bundle (likely parsed from model/behavior definitions) or adjust the callers to extract it from the correct source.

**Link:** [`src/runtime/project_registry.py#L91-L103`](https://github.com/yuzhigang/agent-studio/blob/73b3d169efe036f528c8b0762fb002012c19c37d/src/runtime/project_registry.py#L91-L103)

---

### 3. `MessageHub` lacks thread-safety for mutable state

**Description:** `MessageHub` reads and writes `_subscriptions` and `_projects` without any synchronization. These structures are accessed concurrently from:
- `InboxProcessor` asyncio tasks
- `EventBus.pre_publish_hook` callbacks (which can fire from sandbox threads)
- Main-thread registration and shutdown

A prior commit (`a457761`) fixed the exact same class of thread-safety issue in `EventBus._pre_publish_hooks`.

**Fix:** Add a `threading.RLock` and guard all reads/writes of `_subscriptions` and `_projects`.

**Link:** [`src/runtime/message_hub.py#L13-L46`](https://github.com/yuzhigang/agent-studio/blob/73b3d169efe036f528c8b0762fb002012c19c37d/src/runtime/message_hub.py#L13-L46)

---

### 4. Duplicate supervisor connections enqueue every external event twice

**Description:** `run_command.py` creates both a `JsonRpcChannel` (which registers `notify.externalEvent` internally) and a separate legacy WebSocket connection via `_run_supervisor_client` that also registers `notify.externalEvent`. Since the supervisor broadcasts to every connected client, each external event is received on both connections and enqueued twice in the worker-level inbox.

This violates the CLAUDE.md design principle: "Uses a single `InboxProcessor` / `OutboxProcessor` and one `Channel` per worker".

**Fix:** Remove the `notify.externalEvent` handler from `_register_supervisor_handlers` and rely solely on the `JsonRpcChannel` for inbound external events.

**Link:** [`src/worker/cli/run_command.py#L168-L238`](https://github.com/yuzhigang/agent-studio/blob/73b3d169efe036f528c8b0762fb002012c19c37d/src/worker/cli/run_command.py#L168-L238)

---

### 5. `SQLiteMessageStore` hardcodes `error_count < 10`

**Description:** `SQLiteMessageStore.outbox_read_pending` hardcodes `AND (error_count IS NULL OR error_count < 10)` in its SQL query. `OutboxProcessor` accepts a configurable `max_retries` parameter (default 10). If `max_retries` is changed, the store and processor disagree on which messages are pending, leading to either infinite retries (if `max_retries < 10`) or prematurely suppressed retries (if `max_retries > 10`).

**Fix:** Pass `max_retries` into the `MessageStore` interface or filter pending messages in Python rather than in SQL.

**Link:** [`src/runtime/stores/sqlite_message_store.py#L157-L170`](https://github.com/yuzhigang/agent-studio/blob/73b3d169efe036f528c8b0762fb002012c19c37d/src/runtime/stores/sqlite_message_store.py#L157-L170)

---

### 6. Stale test file `tests/runtime/stores/test_message_store.py` should be deleted

**Description:** This untracked file calls `inbox_enqueue`, `outbox_enqueue`, etc. on `SQLiteStore`, but these per-project `MessageStore` methods were removed in commit `73b3d16` ("chore: remove per-project MessageStore methods from SQLiteStore"). Running this file produces `AttributeError` failures. A correct replacement already exists at `tests/runtime/stores/test_sqlite_message_store.py`.

The implementation plan explicitly stated: "Delete `tests/runtime/stores/test_message_store.py` (old per-project message store tests)."

**Fix:** Delete the file.

**Link:** [`tests/runtime/stores/test_message_store.py#L1-L117`](https://github.com/yuzhigang/agent-studio/blob/73b3d169efe036f528c8b0762fb002012c19c37d/tests/runtime/stores/test_message_store.py#L1-L117)

---

### 7. `run_inline.py` uses wrong worker directory

**Description:** `run_inline.py` hardcodes `"inline"` as the worker directory:

```python
worker_dir = os.path.join(os.path.expanduser("~"), ".agent-studio", "workers", "inline")
```

The implementation plan `docs/superpowers/plans/2026-04-16-message-hub-worker-level.md` explicitly specifies:

```python
worker_dir = os.path.join(os.path.expanduser("~"), ".agent-studio", "workers", str(os.getpid()))
```

Using a static name can cause collisions if multiple inline workers run concurrently.

**Fix:** Replace `"inline"` with `str(os.getpid())`.

**Link:** [`src/worker/cli/run_inline.py#L11`](https://github.com/yuzhigang/agent-studio/blob/73b3d169efe036f528c8b0762fb002012c19c37d/src/worker/cli/run_inline.py#L11)

---

## Recommendations

1. **Fix the N^2 duplication bug first** — it is unambiguous and will break any multi-project worker.
2. **Resolve `model_events` population** — without it, external event routing is completely non-functional.
3. **Add thread-safety locks to `MessageHub`** — given the prior `EventBus` fix, this is a known risk.
4. **Deduplicate supervisor inbound paths** — decide whether `JsonRpcChannel` or `_run_supervisor_client` owns external events, not both.
5. **Align store retry logic** with `OutboxProcessor.max_retries` or make it non-configurable.
6. **Clean up stale artifacts** (`test_message_store.py`, `run_inline.py` directory name).
