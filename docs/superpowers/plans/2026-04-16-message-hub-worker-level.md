# MessageHub Worker-Level Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor MessageHub from a per-world component to a worker-level singleton that intercepts events via `EventBus.pre_publish_hook`, routes external messages through a shared subscription table, and persists inbox/outbox in a worker-level `messagebox.db`.

**Architecture:** 
- A single `MessageHub` instance per worker process registers multiple worlds by attaching `pre_publish_hook`s to their `EventBus` instances.
- A new `SQLiteMessageStore` manages `messagebox.db` (no `world_id` column) for durable inbox/outbox buffering.
- `InboxProcessor` polls the worker-level inbox and broadcasts to all subscribed worlds; `OutboxProcessor` sends all pending messages through the single shared `Channel`.
- Worker CLI (`run_command.py`, `run_inline.py`) creates one MessageHub and registers/unregisters worlds dynamically.

**Tech Stack:** Python 3.11+, asyncio, sqlite3, pytest+anyio

---

## File Structure

| File | Responsibility |
|------|----------------|
| `src/runtime/event_bus.py` | Add `pre_publish_hook` list to `EventBus` |
| `src/runtime/stores/base.py` | Add new `MessageStore` interface **without** `world_id` parameters |
| `src/runtime/stores/sqlite_message_store.py` | New worker-level SQLite store for `messagebox.db` |
| `src/runtime/stores/__init__.py` | Export `SQLiteMessageStore` |
| `src/runtime/message_hub.py` | Rewrite as worker-level singleton with `register_world` / `unregister_world` |
| `src/runtime/inbox_processor.py` | Update to read from worker-level store and broadcast via subscription table |
| `src/runtime/outbox_processor.py` | Update to read from worker-level store |
| `src/worker/cli/run_command.py` | Use single MessageHub; register world before start |
| `src/worker/cli/run_inline.py` | Use single MessageHub; register all worlds before start |
| `tests/runtime/test_event_bus.py` | Add `pre_publish_hook` tests |
| `tests/runtime/stores/test_sqlite_message_store.py` | New tests for worker-level message store |
| `tests/runtime/test_message_hub.py` | Rewrite for worker-level semantics |
| `tests/runtime/test_inbox_processor.py` | Update for multi-world broadcast routing |
| `tests/runtime/test_outbox_processor.py` | Update for worker-level store |

---

## Task 1: EventBus `pre_publish_hook`

**Files:**
- Modify: `src/runtime/event_bus.py`
- Test: `tests/runtime/test_event_bus.py`

- [ ] **Step 1: Write the failing test**

```python
def test_pre_publish_hook_called_on_publish():
    bus = EventBus()
    calls = []
    def hook(event_type, payload, source, scope, target):
        calls.append((event_type, payload, source, scope, target))
    bus.add_pre_publish_hook(hook)
    bus.publish("test.event", {"a": 1}, "src-1", "world", "tgt-1")
    assert len(calls) == 1
    assert calls[0] == ("test.event", {"a": 1}, "src-1", "world", "tgt-1")

def test_remove_pre_publish_hook():
    bus = EventBus()
    calls = []
    def hook(event_type, payload, source, scope, target):
        calls.append(event_type)
    bus.add_pre_publish_hook(hook)
    bus.remove_pre_publish_hook(hook)
    bus.publish("test.event", {}, "src-1", "world")
    assert len(calls) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_event_bus.py::test_pre_publish_hook_called_on_publish -v`
Expected: FAIL with "AttributeError: 'EventBus' object has no attribute 'add_pre_publish_hook'"

- [ ] **Step 3: Write minimal implementation**

In `src/runtime/event_bus.py`, add inside `EventBus.__init__`:
```python
self._pre_publish_hooks: list[Callable] = []
```

Add methods:
```python
def add_pre_publish_hook(self, hook: Callable[[str, dict, str, str, str | None], None]) -> None:
    self._pre_publish_hooks.append(hook)

def remove_pre_publish_hook(self, hook: Callable) -> None:
    self._pre_publish_hooks.remove(hook)
```

In `EventBus.publish`, before the handler loop:
```python
for hook in self._pre_publish_hooks:
    hook(event_type, payload, source, scope, target)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/test_event_bus.py::test_pre_publish_hook_called_on_publish tests/runtime/test_event_bus.py::test_remove_pre_publish_hook -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/runtime/event_bus.py tests/runtime/test_event_bus.py
git commit -m "feat: add EventBus pre_publish_hook"
```

---

## Task 2: Worker-Level `MessageStore` Interface and `SQLiteMessageStore`

**Files:**
- Modify: `src/runtime/stores/base.py`
- Create: `src/runtime/stores/sqlite_message_store.py`
- Modify: `src/runtime/stores/__init__.py`
- Test: `tests/runtime/stores/test_sqlite_message_store.py`

- [ ] **Step 1: Write the new `MessageStore` interface without `world_id`**

In `src/runtime/stores/base.py`, replace the existing `MessageStore` class with:

```python
class MessageStore(ABC):
    @abstractmethod
    def inbox_enqueue(
        self,
        event_type: str,
        payload: dict,
        source: str,
        scope: str,
        target: str | None,
    ) -> int:
        """Append a message to the inbox. Returns the message id."""
        ...

    @abstractmethod
    def inbox_mark_processed(self, message_id: int) -> None:
        """Mark an inbox message as processed."""
        ...

    @abstractmethod
    def inbox_read_pending(self, limit: int) -> list[dict]:
        """Read unprocessed inbox messages ordered by id ascending."""
        ...

    @abstractmethod
    def outbox_enqueue(
        self,
        event_type: str,
        payload: dict,
        source: str,
        scope: str,
        target: str | None,
    ) -> int:
        """Append a message to the outbox. Returns the message id."""
        ...

    @abstractmethod
    def outbox_mark_sent(self, message_id: int) -> None:
        """Mark an outbox message as sent."""
        ...

    @abstractmethod
    def outbox_read_pending(self, limit: int) -> list[dict]:
        """Read unsent outbox messages eligible for sending, ordered by id ascending."""
        ...

    @abstractmethod
    def outbox_update_error(
        self,
        message_id: int,
        error_count: int,
        retry_after: str | None,
        last_error: str | None,
    ) -> None:
        """Update error state for an outbox message."""
        ...
```

- [ ] **Step 2: Create `SQLiteMessageStore`**

Create `src/runtime/stores/sqlite_message_store.py` with the implementation from the codebase patterns (schema without `world_id`, same method signatures as new `MessageStore`).

- [ ] **Step 3: Export `SQLiteMessageStore`**

In `src/runtime/stores/__init__.py`:
```python
from .base import WorldStore, SceneStore, InstanceStore, EventLogStore, MessageStore
from .sqlite_store import SQLiteStore
from .sqlite_message_store import SQLiteMessageStore

__all__ = ["WorldStore", "SceneStore", "InstanceStore", "EventLogStore", "MessageStore", "SQLiteStore", "SQLiteMessageStore"]
```

- [ ] **Step 4: Write failing tests for `SQLiteMessageStore`**

Create `tests/runtime/stores/test_sqlite_message_store.py` covering:
- `inbox_enqueue` + `inbox_read_pending`
- `inbox_mark_processed`
- `outbox_enqueue` + `outbox_read_pending`
- `outbox_mark_sent`
- `outbox_update_error` with future `retry_after` (excluded) and past `retry_after` (included)

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/runtime/stores/test_sqlite_message_store.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/runtime/stores/base.py src/runtime/stores/sqlite_message_store.py src/runtime/stores/__init__.py tests/runtime/stores/test_sqlite_message_store.py
git commit -m "feat: add worker-level SQLiteMessageStore without world_id"
```

---

## Task 3: Rewrite `MessageHub` as Worker-Level Singleton

**Files:**
- Modify: `src/runtime/message_hub.py`
- Test: `tests/runtime/test_message_hub.py`

- [ ] **Step 1: Write the new `MessageHub` implementation**

Replace `src/runtime/message_hub.py` with a worker-level `MessageHub` that:
- Accepts `message_store` and `channel` in `__init__`
- Maintains `_subscriptions: dict[str, set[str]]` and `_worlds: dict[str, tuple[EventBus, Callable]]`
- `register_world(world_id, event_bus, model_events)` updates subscription table and attaches a `pre_publish_hook` that writes `outbox_enqueue` for `external=True` events
- `unregister_world(world_id)` removes hook and cleans subscriptions
- `on_channel_message` writes to inbox
- `start()` / `stop()` manage processors and channel

- [ ] **Step 2: Write failing tests for worker-level `MessageHub`**

Replace `tests/runtime/test_message_hub.py` with tests covering:
- `register_world` adds hook and writes outbox on publish
- `unregister_world` removes hook
- non-external events do not write outbox
- `on_channel_message` writes inbox
- `start`/`stop` manages processors and channel
- `is_ready` behavior

- [ ] **Step 3: Run tests to verify they pass**

Run: `pytest tests/runtime/test_message_hub.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/runtime/message_hub.py tests/runtime/test_message_hub.py
git commit -m "feat: refactor MessageHub to worker-level singleton"
```

---

## Task 4: Update `InboxProcessor` for Worker-Level Multi-World Broadcast

**Files:**
- Modify: `src/runtime/inbox_processor.py`
- Test: `tests/runtime/test_inbox_processor.py`

- [ ] **Step 1: Rewrite `InboxProcessor`**

Replace `src/runtime/inbox_processor.py`:

```python
import asyncio


class InboxProcessor:
    def __init__(self, message_hub, poll_interval: float = 1.0, batch_size: int = 100):
        self._hub = message_hub
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        store = self._hub._msg_store
        while not self._stop_event.is_set():
            try:
                messages = store.inbox_read_pending(self._batch_size)
                for msg in messages:
                    if self._stop_event.is_set():
                        break
                    success = self._distribute(msg)
                    if success:
                        store.inbox_mark_processed(msg["id"])
            except Exception:
                pass
            await asyncio.sleep(self._poll_interval)

    def _distribute(self, msg: dict) -> bool:
        event_type = msg["event_type"]
        world_ids = self._hub._subscriptions.get(event_type, set())
        if not world_ids:
            # No subscribers: mark processed to avoid dead messages
            return True
        any_failed = False
        for world_id in world_ids:
            event_bus, _hook = self._hub._worlds.get(world_id, (None, None))
            if event_bus is None:
                continue
            try:
                event_bus.publish(
                    event_type,
                    msg["payload"],
                    msg["source"],
                    msg["scope"],
                    msg.get("target"),
                )
            except Exception:
                any_failed = True
        return not any_failed
```

- [ ] **Step 2: Rewrite tests for `InboxProcessor`**

Replace `tests/runtime/test_inbox_processor.py`:

```python
import asyncio
import pytest
from src.runtime.event_bus import EventBus
from src.runtime.message_hub import MessageHub
from src.runtime.stores.sqlite_message_store import SQLiteMessageStore


@pytest.fixture
def msg_store(tmp_path):
    s = SQLiteMessageStore(str(tmp_path / "worker"))
    yield s
    s.close()


@pytest.mark.anyio
async def test_inbox_processor_broadcasts_to_subscribed_worlds(msg_store):
    hub = MessageHub(msg_store, None)
    bus_a = EventBus()
    bus_b = EventBus()
    hub.register_world("proj-a", bus_a, {"ext.event": {"external": True}})
    hub.register_world("proj-b", bus_b, {"ext.event": {"external": True}})

    received_a = []
    received_b = []
    bus_a.register("inst-a", "world", "ext.event", lambda t, p, s: received_a.append((t, p, s)))
    bus_b.register("inst-b", "world", "ext.event", lambda t, p, s: received_b.append((t, p, s)))

    msg_store.inbox_enqueue("ext.event", {"val": 42}, "src-x", "world", None)

    await hub.start()
    await asyncio.sleep(0.3)
    await hub.stop()

    assert len(received_a) == 1
    assert len(received_b) == 1
    pending = msg_store.inbox_read_pending(10)
    assert len(pending) == 0


@pytest.mark.anyio
async def test_inbox_processor_skips_unsubscribed_worlds(msg_store):
    hub = MessageHub(msg_store, None)
    bus_a = EventBus()
    bus_b = EventBus()
    hub.register_world("proj-a", bus_a, {"ext.event": {"external": True}})
    hub.register_world("proj-b", bus_b, {"other.event": {"external": True}})

    received_a = []
    received_b = []
    bus_a.register("inst-a", "world", "ext.event", lambda t, p, s: received_a.append((t, p, s)))
    bus_b.register("inst-b", "world", "ext.event", lambda t, p, s: received_b.append((t, p, s)))

    msg_store.inbox_enqueue("ext.event", {"val": 1}, "src-x", "world", None)

    await hub.start()
    await asyncio.sleep(0.3)
    await hub.stop()

    assert len(received_a) == 1
    assert len(received_b) == 0
    pending = msg_store.inbox_read_pending(10)
    assert len(pending) == 0


@pytest.mark.anyio
async def test_inbox_processor_no_subscribers_marks_processed(msg_store):
    hub = MessageHub(msg_store, None)

    msg_store.inbox_enqueue("ext.event", {"val": 1}, "src-x", "world", None)

    await hub.start()
    await asyncio.sleep(0.3)
    await hub.stop()

    pending = msg_store.inbox_read_pending(10)
    assert len(pending) == 0
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `pytest tests/runtime/test_inbox_processor.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/runtime/inbox_processor.py tests/runtime/test_inbox_processor.py
git commit -m "feat: update InboxProcessor for worker-level broadcast routing"
```

---

## Task 5: Update `OutboxProcessor` for Worker-Level Store

**Files:**
- Modify: `src/runtime/outbox_processor.py`
- Test: `tests/runtime/test_outbox_processor.py`

- [ ] **Step 1: Rewrite `OutboxProcessor`**

Replace `src/runtime/outbox_processor.py`:

```python
import asyncio
from datetime import datetime, timedelta, timezone

from src.worker.channels.base import SendResult


class OutboxProcessor:
    def __init__(
        self,
        message_hub,
        poll_interval: float = 1.0,
        batch_size: int = 100,
        max_retries: int = 10,
        max_retry_interval: float = 30.0,
    ):
        self._hub = message_hub
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._max_retries = max_retries
        self._max_retry_interval = max_retry_interval
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        store = self._hub._msg_store
        channel = self._hub._channel
        while not self._stop_event.is_set():
            try:
                if channel is None:
                    await asyncio.sleep(self._poll_interval)
                    continue
                messages = store.outbox_read_pending(self._batch_size)
                for msg in messages:
                    if self._stop_event.is_set():
                        break
                    result = await channel.send(
                        event_type=msg["event_type"],
                        payload=msg["payload"],
                        source=msg["source"],
                        scope=msg["scope"],
                        target=msg.get("target"),
                    )
                    if result == SendResult.SUCCESS:
                        store.outbox_mark_sent(msg["id"])
                    elif result == SendResult.RETRYABLE:
                        error_count = msg.get("error_count", 0) + 1
                        backoff = min(2 ** error_count, self._max_retry_interval)
                        retry_dt = datetime.now(timezone.utc) + timedelta(seconds=backoff)
                        store.outbox_update_error(
                            msg["id"],
                            error_count=error_count,
                            retry_after=retry_dt.isoformat(),
                            last_error=None,
                        )
                    elif result == SendResult.PERMANENT:
                        store.outbox_update_error(
                            msg["id"],
                            error_count=self._max_retries,
                            retry_after=None,
                            last_error="permanent failure",
                        )
            except Exception:
                pass
            await asyncio.sleep(self._poll_interval)
```

- [ ] **Step 2: Rewrite tests for `OutboxProcessor`**

Replace `tests/runtime/test_outbox_processor.py`:

```python
import asyncio
import pytest
from src.runtime.message_hub import MessageHub
from src.runtime.stores.sqlite_message_store import SQLiteMessageStore
from src.worker.channels.base import SendResult


@pytest.fixture
def msg_store(tmp_path):
    s = SQLiteMessageStore(str(tmp_path / "worker"))
    yield s
    s.close()


class FakeChannel:
    def __init__(self, result=SendResult.SUCCESS):
        self.result = result
        self.sent = []
        self._ready = True

    async def start(self, inbound_callback):
        pass

    async def stop(self):
        pass

    def is_ready(self):
        return self._ready

    async def send(self, event_type, payload, source, scope, target):
        self.sent.append({"event_type": event_type, "payload": payload, "source": source, "scope": scope, "target": target})
        return self.result


@pytest.mark.anyio
async def test_outbox_processor_sends_and_marks_sent(msg_store):
    channel = FakeChannel(SendResult.SUCCESS)
    hub = MessageHub(msg_store, channel)

    msg_store.outbox_enqueue("order.shipped", {"id": "1"}, "inst-1", "world", None)

    await hub.start()
    await asyncio.sleep(0.3)
    await hub.stop()

    assert len(channel.sent) == 1
    assert channel.sent[0]["event_type"] == "order.shipped"
    assert len(msg_store.outbox_read_pending(10)) == 0


@pytest.mark.anyio
async def test_outbox_processor_retries_on_retryable(msg_store):
    channel = FakeChannel(SendResult.RETRYABLE)
    hub = MessageHub(msg_store, channel)

    msg_store.outbox_enqueue("order.failed", {"id": "2"}, "inst-1", "world", None)

    await hub.start()
    await asyncio.sleep(0.3)
    await hub.stop()

    assert len(channel.sent) == 1
    assert len(msg_store.outbox_read_pending(10)) == 0  # retry_after is in future

    row = msg_store._conn.execute("SELECT error_count, retry_after, last_error FROM outbox WHERE id = 1").fetchone()
    assert row[0] == 1
    assert row[1] is not None
    assert row[2] is None


@pytest.mark.anyio
async def test_outbox_processor_permanent_failure(msg_store):
    channel = FakeChannel(SendResult.PERMANENT)
    hub = MessageHub(msg_store, channel)

    msg_store.outbox_enqueue("order.bad", {"id": "3"}, "inst-1", "world", None)

    await hub.start()
    await asyncio.sleep(0.3)
    await hub.stop()

    assert len(channel.sent) == 1
    assert len(msg_store.outbox_read_pending(10)) == 0

    row = msg_store._conn.execute("SELECT error_count, last_error FROM outbox WHERE id = 1").fetchone()
    assert row[0] == 10
    assert row[1] == "permanent failure"


@pytest.mark.anyio
async def test_outbox_processor_no_channel_does_not_crash(msg_store):
    hub = MessageHub(msg_store, None)

    msg_store.outbox_enqueue("order.shipped", {"id": "1"}, "inst-1", "world", None)

    await hub.start()
    await asyncio.sleep(0.2)
    await hub.stop()

    assert len(msg_store.outbox_read_pending(10)) == 1
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `pytest tests/runtime/test_outbox_processor.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/runtime/outbox_processor.py tests/runtime/test_outbox_processor.py
git commit -m "feat: update OutboxProcessor for worker-level store"
```

---

## Task 6: Update Worker CLI for Single MessageHub

**Files:**
- Modify: `src/worker/cli/run_command.py`
- Modify: `src/worker/cli/run_inline.py`
- Modify: `tests/worker/cli/test_run_inline.py`

- [ ] **Step 1: Update `run_command.py`**

In `src/worker/cli/run_command.py`:
- Remove per-world MessageHub creation inside `run_world`.
- Create a single `MessageHub` after loading the bundle.
- Register the world: `message_hub.register_world(world_id, bus, bundle.get("model_events", {}))`.
- Pass `message_hub` to `InstanceManager` via constructor if possible, or set `bundle["instance_manager"]._message_hub = message_hub`.
- Start `message_hub` before other async tasks.
- In `_graceful_shutdown`, stop `message_hub` **before** unregistering world.

Example diff pattern:
```python
from src.runtime.stores.sqlite_message_store import SQLiteMessageStore

# ...

def run_world(...):
    # ... load bundle ...
    worker_dir = os.path.join(os.path.expanduser("~"), ".agent-studio", "workers", str(os.getpid()))
    msg_store = SQLiteMessageStore(worker_dir)
    channel = JsonRpcChannel(supervisor_ws) if supervisor_ws else None
    message_hub = MessageHub(msg_store, channel)

    bus = bundle["event_bus_registry"].get_or_create(world_id)
    message_hub.register_world(world_id, bus, bundle.get("model_events", {}))
    bundle["instance_manager"]._message_hub = message_hub

    # ... signal handlers, loop setup ...
    async def _start_and_run():
        await message_hub.start()
        try:
            await asyncio.Future()
        finally:
            await message_hub.stop()
```

- [ ] **Step 2: Update `run_inline.py`**

In `src/worker/cli/run_inline.py`:
- Create one `MessageHub` before the loop over `world_dirs`.
- For each world, register it on the shared `message_hub`.
- In `_shutdown`, stop `message_hub` first, then unload worlds.

```python
def run_inline(world_dirs):
    worker_dir = os.path.join(os.path.expanduser("~"), ".agent-studio", "workers", str(os.getpid()))
    msg_store = SQLiteMessageStore(worker_dir)
    message_hub = MessageHub(msg_store, None)
    bundles = _load_worlds(world_dirs, message_hub)
    # ... shutdown handler stops message_hub before unloading ...
```

- [ ] **Step 3: Update `tests/worker/cli/test_run_inline.py`**

Update the test to assert that a single `MessageHub` is created and shared across bundles, and that each bundle's world is registered.

- [ ] **Step 4: Run full test suite for worker CLI**

Run: `pytest tests/worker/cli/test_run_inline.py tests/worker/cli/test_run_command.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/worker/cli/run_command.py src/worker/cli/run_inline.py tests/worker/cli/test_run_inline.py
git commit -m "feat: use single worker-level MessageHub in CLI"
```

---

## Task 7: Full Regression Test and Cleanup

- [ ] **Step 1: Run all tests**

Run: `pytest tests/ -v`
Expected: All 140+ tests pass.

- [ ] **Step 2: Remove deprecated per-world inbox/outbox from `SQLiteStore` (optional but recommended)**

If the old `MessageStore` methods on `SQLiteStore` are no longer referenced anywhere, remove:
- `inbox` and `outbox` table creation from `SQLiteStore._ensure_schema`
- `MessageStore` from `SQLiteStore` base classes
- All `inbox_*` and `outbox_*` methods from `SQLiteStore`

Then delete `tests/runtime/stores/test_message_store.py` (the old per-world message store tests).

Run tests again to confirm nothing breaks.

- [ ] **Step 3: Final commit**

```bash
git add src/runtime/stores/sqlite_store.py src/runtime/stores/__init__.py tests/runtime/stores/test_message_store.py
git commit -m "chore: remove per-world MessageStore methods from SQLiteStore"
```

---

## Review Loop

After completing the plan document:

1. Dispatch a single plan-document-reviewer subagent with:
   - path to this plan document
   - path to `docs/superpowers/specs/2026-04-16-message-hub-worker-level-design.md`
2. If issues found: fix and re-dispatch reviewer.
3. If approved: proceed to execution with @superpowers:subagent-driven-development or @superpowers:executing-plans.



