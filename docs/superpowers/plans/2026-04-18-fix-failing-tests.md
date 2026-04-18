# Fix Failing Tests Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Fix all 12 failing tests across the codebase (148 passing, 1 skipped).

**Architecture:** Four independent bug categories: stale message-store tests, process-level lock semantics, websockets 13+ API breakage, and a flaky filesystem watcher test.

**Tech Stack:** Python 3.13, pytest, websockets 16.0, fasteners, watchdog

---

### Task 1: Remove Stale message_store Tests

**Files:**
- Delete: `tests/runtime/stores/test_message_store.py`

The test file references `SQLiteStore.inbox_enqueue` / `outbox_enqueue` methods that were removed when inbox/outbox moved to worker-level `SQLiteMessageStore`. `SQLiteMessageStore` is already fully tested in `tests/runtime/stores/test_sqlite_message_store.py`.

- [ ] **Step 1: Delete the stale test file**

```bash
git rm tests/runtime/stores/test_message_store.py
```

- [ ] **Step 2: Verify no references remain**

```bash
uv run pytest tests/runtime/stores/ -v
```

Expected: All 8 sqlite_store / sqlite_message_store tests PASS.

- [ ] **Step 3: Commit**

```bash
git commit -m "test: remove stale message_store tests (moved to SQLiteMessageStore)"
```

---

### Task 2: Fix WorldLock Same-Process Mutual Exclusion

**Files:**
- Modify: `src/runtime/locks/world_lock.py`
- Test: `tests/runtime/locks/test_world_lock.py`

`fasteners.InterProcessLock` uses OS-level file locking (`flock`), which does **not** block additional acquisitions from the **same process**. `test_second_acquire_raises` expects it to.

- [ ] **Step 1: Write the failing test** (already exists)

Run: `uv run pytest tests/runtime/locks/test_world_lock.py::test_second_acquire_raises -v`
Expected: FAIL

- [ ] **Step 2: Add in-process lock tracking to WorldLock**

Use a class-level `dict` + `threading.Lock` to track which world directories are already held by the current process.

```python
class WorldLock:
    _in_process_locks: dict[str, int] = {}
    _in_process_locks_lock = threading.Lock()
    ...
```

In `acquire()`, check / increment the dict before the file lock. In `release()`, decrement / remove.

- [ ] **Step 3: Run the test**

Run: `uv run pytest tests/runtime/locks/test_world_lock.py -v`
Expected: All 3 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add src/runtime/locks/world_lock.py
git commit -m "fix: WorldLock prevents double-acquire in same process"
```

---

### Task 3: Fix JsonRpcConnection for websockets 13+ API

**Files:**
- Modify: `src/worker/server/jsonrpc_ws.py`
- Test: `tests/worker/channels/test_jsonrpc_channel.py`

`websockets` 13+ replaced `WebSocketClientProtocol` with `ClientConnection`, which **removed** the `.closed` property. `JsonRpcConnection.send()` does `if not self._ws.closed:`; this raises `AttributeError`, which is swallowed by the caller's broad `except Exception`, causing all sends to return `RETRYABLE`.

- [ ] **Step 1: Run the failing test**

Run: `uv run pytest tests/worker/channels/test_jsonrpc_channel.py::test_jsonrpc_channel_send_success -v`
Expected: FAIL with `AssertionError: RETRYABLE != SUCCESS`

- [ ] **Step 2: Update `JsonRpcConnection` to use `.state`**

Replace `self._ws.closed` checks with `self._ws.state == State.OPEN` (import `State` from `websockets.protocol`).

- [ ] **Step 3: Run the test**

Run: `uv run pytest tests/worker/channels/test_jsonrpc_channel.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add src/worker/server/jsonrpc_ws.py
git commit -m "fix: JsonRpcConnection compatible with websockets 13+ (removed .closed)"
```

---

### Task 4: Fix Flaky LibWatcher Hot-Reload Test

**Files:**
- Modify: `tests/runtime/lib/test_watcher.py`

On macOS with FSEvents, watchdog can take >5 s to fire `on_modified` for an existing file. The test currently spins 50 x 0.1 s = 5 s.

- [ ] **Step 1: Run the failing test**

Run: `uv run pytest tests/runtime/lib/test_watcher.py::test_watcher_detects_file_change -v`
Expected: FAIL with `hot reload did not occur`

- [ ] **Step 2: Increase timeout and add PollingObserver fallback**

Switch `LibWatcher` in the test to use `watchdog.observers.polling.PollingObserver` (deterministic, slower but reliable in CI). Alternatively, increase the retry loop from 50 to 100 iterations (10 s).

Preferred fix: modify `LibWatcher` to accept an optional `observer_class` kwarg, and have the test inject `PollingObserver`.

- [ ] **Step 3: Run the test**

Run: `uv run pytest tests/runtime/lib/test_watcher.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/runtime/lib/watcher.py tests/runtime/lib/test_watcher.py
git commit -m "fix: stabilize watcher hot-reload test with PollingObserver"
```

---

### Task 5: Full Regression Run

- [ ] **Step 1: Run the entire test suite**

Run: `uv run pytest tests/ -v --tb=short`
Expected: 157+ collected, 0 failed, 1 skipped.

- [ ] **Step 2: Commit if clean**

```bash
git add docs/superpowers/plans/2026-04-18-fix-failing-tests.md
git commit -m "docs: add test-fix plan"
```
