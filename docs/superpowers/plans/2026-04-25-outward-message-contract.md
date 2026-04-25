# Outward Message Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the outward/inbound message contract from `world_id`-based routing to `source_world` / `target_world`, remove `targetWorldId` from `triggerEvent external=true`, and keep world-internal routing expressed by `scope + target`.

**Architecture:** The change is a contract migration, not a new subsystem. First update the envelope/store layer so persisted messages carry `source_world` and `target_world`; then switch sender/emitter/action code to the new outward semantics; then move inbound routing to `target_world`; finally update tests and docs so the old contract is fully removed. Keep `EventBus` behavior unchanged except for receiving the renamed `target` semantics through the existing ingress path.

**Tech Stack:** Python 3, dataclasses, sqlite3, pytest

---

## File Map

- `src/runtime/messaging/envelope.py`
  - Defines `MessageEnvelope`; replace `world_id` with `source_world` / `target_world`.
- `src/runtime/messaging/store.py`
  - Store protocol signatures for inbox/outbox records and world-delivery helpers.
- `src/runtime/messaging/sqlite_store.py`
  - SQLite schema, row mapping, insert/select logic for inbox/outbox.
- `src/runtime/messaging/world_sender.py`
  - Outbound sender; stop accepting target world and always stamp current source world.
- `src/runtime/world_event_emitter.py`
  - Outward publish facade; remove target-world parameter from `publish_external`.
- `src/runtime/instance_manager.py`
  - `triggerEvent external=true` validation, payload evaluation, and emitter call.
- `src/runtime/messaging/hub.py`
  - JSON-RPC/message-envelope construction and world registration behavior.
- `src/runtime/messaging/inbox_processor.py`
  - Route inbound messages by `target_world` instead of `world_id`.
- `src/runtime/messaging/world_ingress.py`
  - Preserve `source_world` through ingress and pass `target` to EventBus unchanged.
- `src/worker/manager.py`
  - Worker-side envelope construction for inbound commands/tests.
- `tests/runtime/messaging/test_envelope.py`
  - Envelope field expectations.
- `tests/runtime/messaging/test_sqlite_store.py`
  - Persistence expectations for renamed columns and values.
- `tests/runtime/messaging/test_world_sender.py`
  - Outbound sender semantics (`source_world` set, `target_world is None`).
- `tests/runtime/messaging/test_hub.py`
  - Registration/routing semantics if they mention world fields.
- `tests/runtime/messaging/test_inbox_processor.py`
  - `target_world` routing, broadcast, and `source_world` retention.
- `tests/runtime/messaging/test_world_ingress.py`
  - Ingress preserves `source_world` while forwarding strict delivery.
- `tests/runtime/test_instance_manager.py`
  - `triggerEvent external=true` contract and removal of `targetWorldId`.
- `tests/runtime/test_message_hub.py`
  - Compatibility checks for renamed envelope fields.
- `tests/worker/test_manager.py`
  - Worker-level envelope construction if fields are asserted directly.
- `docs/superpowers/specs/2026-04-25-outward-message-contract-design.md`
  - Already approved spec; only touch if implementation reveals a contradiction.

### Task 1: Rename MessageEnvelope and persistence fields

**Files:**
- Modify: `src/runtime/messaging/envelope.py`
- Modify: `src/runtime/messaging/store.py`
- Modify: `src/runtime/messaging/sqlite_store.py`
- Test: `tests/runtime/messaging/test_envelope.py`
- Test: `tests/runtime/messaging/test_sqlite_store.py`

- [ ] **Step 1: Write the failing envelope/store tests**

```python
def test_message_envelope_fields_are_source_and_target_world():
    envelope = MessageEnvelope(
        message_id="msg-1",
        source_world="world-a",
        target_world="world-b",
        event_type="ladle.loaded",
        payload={"ladleId": "L1"},
        source="ladle-001",
        scope="scene:scene-a",
        target="ladle-002",
        trace_id="trace-1",
        headers={"priority": "high"},
    )

    assert envelope.source_world == "world-a"
    assert envelope.target_world == "world-b"
    assert envelope.target == "ladle-002"


def test_sqlite_store_round_trips_source_world_and_target_world(tmp_path):
    store = SQLiteMessageStore(str(tmp_path / "messagebox.db"))
    envelope = MessageEnvelope(
        message_id="msg-1",
        source_world="world-a",
        target_world="world-b",
        event_type="ladle.loaded",
        payload={"ladleId": "L1"},
        source="ladle-001",
        scope="world",
        target="ladle-002",
        trace_id="trace-1",
        headers={"priority": "high"},
    )

    store.outbox_append(envelope)
    stored = store.outbox_read_pending(10)[0]

    assert stored.source_world == "world-a"
    assert stored.target_world == "world-b"
    assert stored.target == "ladle-002"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/runtime/messaging/test_envelope.py tests/runtime/messaging/test_sqlite_store.py -v`

Expected: FAIL with `TypeError` / attribute errors mentioning missing `source_world` or `target_world`, or sqlite column mismatches still using `world_id`.

- [ ] **Step 3: Write the minimal implementation**

`src/runtime/messaging/envelope.py`

```python
@dataclass
class MessageEnvelope:
    message_id: str
    source_world: str | None = None
    target_world: str | None = None
    event_type: str = ""
    payload: dict = field(default_factory=dict)
    source: str | None = None
    scope: str = "world"
    target: str | None = None
    trace_id: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
```

`src/runtime/messaging/sqlite_store.py`

```python
CREATE TABLE inbox (
    message_id TEXT PRIMARY KEY,
    source_world TEXT,
    target_world TEXT,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    source TEXT,
    scope TEXT NOT NULL DEFAULT 'world',
    target TEXT,
    trace_id TEXT,
    headers TEXT NOT NULL DEFAULT '{}',
    received_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
)

CREATE TABLE outbox (
    message_id TEXT PRIMARY KEY,
    source_world TEXT,
    target_world TEXT,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    source TEXT,
    scope TEXT NOT NULL DEFAULT 'world',
    target TEXT,
    trace_id TEXT,
    headers TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    error_count INTEGER NOT NULL DEFAULT 0,
    retry_after TEXT,
    last_error TEXT,
    sent_at TEXT
)
```

Also update every row-mapping site to read/write `source_world` and `target_world` instead of `world_id`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/runtime/messaging/test_envelope.py tests/runtime/messaging/test_sqlite_store.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/runtime/messaging/envelope.py src/runtime/messaging/store.py src/runtime/messaging/sqlite_store.py tests/runtime/messaging/test_envelope.py tests/runtime/messaging/test_sqlite_store.py
git commit -m "refactor: rename message envelope world routing fields"
```

### Task 2: Switch outward publish to source-world semantics

**Files:**
- Modify: `src/runtime/messaging/world_sender.py`
- Modify: `src/runtime/world_event_emitter.py`
- Modify: `src/runtime/instance_manager.py`
- Test: `tests/runtime/messaging/test_world_sender.py`
- Test: `tests/runtime/test_instance_manager.py`

- [ ] **Step 1: Write the failing outward publish tests**

```python
def test_world_sender_stamps_source_world_and_no_target_world(tmp_path):
    store = SQLiteMessageStore(str(tmp_path / "messagebox.db"))
    hub = MessageHub(store, channel=None)
    sender = WorldMessageSender(world_id="world-a", hub=hub, source="ladle-001")

    sender.send(
        "ladle.loaded",
        {"ladleId": "L1"},
        scope="scene:scene-a",
        target="ladle-002",
        trace_id="trace-1",
        headers={"priority": "high"},
    )

    stored = store.outbox_read_pending(10)[0]
    assert stored.source_world == "world-a"
    assert stored.target_world is None
    assert stored.target == "ladle-002"


def test_external_trigger_event_rejects_target_world_id_and_uses_new_contract():
    emitter_calls = []

    class FakeEmitter:
        def publish_external(self, **kwargs):
            emitter_calls.append(kwargs)
            return "msg-1"

    mgr = InstanceManager(EventBusRegistry(), world_event_emitter=FakeEmitter())
    inst = mgr.create(
        world_id="world-a",
        model_name="ladle",
        instance_id="ladle-001",
        scope="scene:scene-a",
        model={},
    )

    action = {
        "type": "triggerEvent",
        "name": "ladle.loaded",
        "external": True,
        "scope": "scene:scene-a",
        "target": "ladle-002",
        "payload": {"ladleId": "this.id"},
        "headers": {"priority": "high"},
    }

    mgr._execute_action(inst, action, {}, "external")

    assert emitter_calls == [{
        "event_type": "ladle.loaded",
        "payload": {"ladleId": "ladle-001"},
        "scope": "scene:scene-a",
        "target": "ladle-002",
        "trace_id": None,
        "headers": {"priority": "high"},
    }]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/runtime/messaging/test_world_sender.py tests/runtime/test_instance_manager.py -v`

Expected: FAIL because `WorldMessageSender.send()` still requires a target world parameter and `InstanceManager` still reads `targetWorldId`.

- [ ] **Step 3: Write the minimal implementation**

`src/runtime/messaging/world_sender.py`

```python
def send(
    self,
    event_type: str,
    payload: dict,
    *,
    scope: str = "world",
    target: str | None = None,
    trace_id: str | None = None,
    headers: dict[str, str] | None = None,
) -> str:
    envelope = MessageEnvelope(
        message_id=str(uuid.uuid4()),
        source_world=self._world_id,
        target_world=None,
        event_type=event_type,
        payload=payload,
        source=self._source,
        scope=scope,
        target=target,
        trace_id=trace_id,
        headers=headers or {},
    )
    self._hub.enqueue_outbound(envelope)
    return envelope.message_id
```

`src/runtime/world_event_emitter.py`

```python
def publish_external(
    self,
    *,
    event_type: str,
    payload: dict,
    scope: str = "world",
    target: str | None = None,
    trace_id: str | None = None,
    headers: dict[str, str] | None = None,
) -> str:
    if self._sender is None:
        raise RuntimeError("WorldEventEmitter has no bound WorldMessageSender")
    return self._sender.send(
        event_type,
        payload,
        scope=scope,
        target=target,
        trace_id=trace_id,
        headers=headers,
    )
```

`src/runtime/instance_manager.py`

```python
if action.get("external") is True:
    if self._event_emitter is None:
        raise RuntimeError("External triggerEvent requires a configured WorldEventEmitter")
    if not event_name:
        raise ValueError("External triggerEvent requires name")
    scope = action.get("scope", instance.scope)
    target = action.get("target")
    trace_id = action.get("traceId")
    headers = action.get("headers") or {}
    if scope != "world" and not (isinstance(scope, str) and scope.startswith("scene:")):
        raise ValueError("External triggerEvent scope must be 'world' or 'scene:<scene_id>'")
    if target is not None and not isinstance(target, str):
        raise ValueError("External triggerEvent target must be a string when provided")
    if trace_id is not None and not isinstance(trace_id, str):
        raise ValueError("External triggerEvent traceId must be a string when provided")
    if not isinstance(headers, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in headers.items()):
        raise ValueError("External triggerEvent headers must be a dict[str, str]")
    self._event_emitter.publish_external(
        event_type=event_name,
        payload=evaluated,
        scope=scope,
        target=target,
        trace_id=trace_id,
        headers=headers,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/runtime/messaging/test_world_sender.py tests/runtime/test_instance_manager.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/runtime/messaging/world_sender.py src/runtime/world_event_emitter.py src/runtime/instance_manager.py tests/runtime/messaging/test_world_sender.py tests/runtime/test_instance_manager.py
git commit -m "refactor: align outward triggerEvent contract"
```

### Task 3: Route inbound delivery by target_world and preserve source_world

**Files:**
- Modify: `src/runtime/messaging/inbox_processor.py`
- Modify: `src/runtime/messaging/hub.py`
- Modify: `src/runtime/messaging/world_ingress.py`
- Modify: `src/worker/manager.py`
- Test: `tests/runtime/messaging/test_inbox_processor.py`
- Test: `tests/runtime/messaging/test_world_ingress.py`
- Test: `tests/runtime/test_message_hub.py`

- [ ] **Step 1: Write the failing inbound routing tests**

```python
@pytest.mark.asyncio
async def test_inbox_processor_routes_by_target_world_and_broadcasts_star(tmp_path):
    store = SQLiteMessageStore(str(tmp_path / "messagebox.db"))
    hub = MessageHub(store, channel=None)
    delivered = []

    class Receiver:
        async def receive(self, envelope):
            delivered.append((envelope.source_world, envelope.target_world, envelope.event_type))

    hub.register_world("world-a", Receiver())
    hub.register_world("world-b", Receiver())

    store.inbox_append(MessageEnvelope(
        message_id="msg-1",
        source_world="external-a",
        target_world="world-a",
        event_type="ladle.loaded",
        payload={},
    ))
    store.inbox_append(MessageEnvelope(
        message_id="msg-2",
        source_world="external-b",
        target_world="*",
        event_type="ladle.synced",
        payload={},
    ))

    processor = InboxProcessor(hub, batch_size=10)
    await processor.run_once()

    assert ("external-a", "world-a", "ladle.loaded") in delivered
    assert delivered.count(("external-b", "*", "ladle.synced")) == 2


@pytest.mark.asyncio
async def test_world_ingress_preserves_source_world():
    calls = []

    class FakeEmitter:
        def publish_internal(self, **kwargs):
            calls.append(kwargs)

    ingress = WorldMessageIngress(FakeEmitter())
    await ingress.receive(MessageEnvelope(
        message_id="msg-1",
        source_world="world-a",
        target_world="world-b",
        event_type="ladle.loaded",
        payload={"ladleId": "L1"},
        source="ladle-001",
        scope="scene:scene-a",
        target="ladle-002",
    ))

    assert calls == [{
        "event_type": "ladle.loaded",
        "payload": {"ladleId": "L1"},
        "source": "ladle-001",
        "scope": "scene:scene-a",
        "target": "ladle-002",
        "raise_on_error": True,
    }]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/runtime/messaging/test_inbox_processor.py tests/runtime/messaging/test_world_ingress.py tests/runtime/test_message_hub.py -v`

Expected: FAIL because inbox expansion/routing still keys off `world_id` and envelope construction still does not carry `source_world` / `target_world`.

- [ ] **Step 3: Write the minimal implementation**

`src/runtime/messaging/inbox_processor.py`

```python
if envelope.target_world == "*":
    targets = sorted(self._hub.list_registered_world_ids())
elif envelope.target_world:
    targets = [envelope.target_world]
else:
    return
```

`src/worker/manager.py`

```python
return MessageEnvelope(
    message_id=params.get("message_id") or params.get("id") or str(uuid.uuid4()),
    source_world=params.get("source_world"),
    target_world=params.get("target_world", default_world_id),
    event_type=params.get("event_type", ""),
    payload=params.get("payload", {}),
    source=params.get("source"),
    scope=params.get("scope", "world"),
    target=params.get("target"),
    trace_id=params.get("trace_id"),
    headers=params.get("headers") or {},
)
```

Ensure every inbox delivery lookup, expansion, and test fixture now references `target_world`, while `WorldMessageIngress` keeps forwarding `source`, `scope`, and `target` without rewriting them.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/runtime/messaging/test_inbox_processor.py tests/runtime/messaging/test_world_ingress.py tests/runtime/test_message_hub.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/runtime/messaging/inbox_processor.py src/runtime/messaging/hub.py src/runtime/messaging/world_ingress.py src/worker/manager.py tests/runtime/messaging/test_inbox_processor.py tests/runtime/messaging/test_world_ingress.py tests/runtime/test_message_hub.py
git commit -m "refactor: route inbound messaging by target world"
```

### Task 4: Remove old contract from fixtures, assertions, and regression tests

**Files:**
- Modify: `tests/runtime/test_inbox_processor.py`
- Modify: `tests/runtime/test_outbox_processor.py`
- Modify: `tests/runtime/test_world_registry.py`
- Modify: `tests/worker/test_manager.py`
- Modify: `tests/worker/channels/test_jsonrpc_channel.py`
- Modify: any remaining runtime/worker tests that mention `world_id` on `MessageEnvelope`

- [ ] **Step 1: Write one failing regression test that proves old contract is gone**

```python
def test_external_trigger_event_no_longer_accepts_target_world_id():
    mgr = InstanceManager(EventBusRegistry(), world_event_emitter=object())
    inst = mgr.create(
        world_id="world-a",
        model_name="ladle",
        instance_id="ladle-001",
        scope="world",
        model={},
    )

    action = {
        "type": "triggerEvent",
        "name": "ladle.loaded",
        "external": True,
        "targetWorldId": "world-b",
        "payload": {},
    }

    with pytest.raises(ValueError, match="targetWorldId is not supported"):
        mgr._execute_action(inst, action, {}, "external")
```

- [ ] **Step 2: Run the focused regression test to verify it fails**

Run: `pytest tests/runtime/test_instance_manager.py::test_external_trigger_event_no_longer_accepts_target_world_id -v`

Expected: FAIL because old fields are ignored or still partially accepted.

- [ ] **Step 3: Write the minimal implementation and test updates**

`src/runtime/instance_manager.py`

```python
if action.get("external") is True and "targetWorldId" in action:
    raise ValueError("External triggerEvent targetWorldId is not supported")
```

Then update remaining tests and fixtures to stop constructing `MessageEnvelope(world_id=...)` and instead use:

```python
MessageEnvelope(
    message_id="msg-1",
    source_world="world-a",
    target_world="world-b",
    event_type="ladle.loaded",
    payload={},
    source="ladle-001",
    scope="world",
    target=None,
)
```

Also update channel serialization assertions to include:

```python
{
    "source_world": "world-a",
    "target_world": "world-b",
    "target": "ladle-002",
}
```

- [ ] **Step 4: Run the full focused regression suite**

Run: `pytest tests/runtime/test_instance_manager.py tests/runtime/test_inbox_processor.py tests/runtime/test_outbox_processor.py tests/runtime/test_world_registry.py tests/worker/test_manager.py tests/worker/channels/test_jsonrpc_channel.py -v`

Expected: PASS, except any environment-specific dependency skips already known in this repo.

- [ ] **Step 5: Commit**

```bash
git add src/runtime/instance_manager.py tests/runtime/test_instance_manager.py tests/runtime/test_inbox_processor.py tests/runtime/test_outbox_processor.py tests/runtime/test_world_registry.py tests/worker/test_manager.py tests/worker/channels/test_jsonrpc_channel.py
git commit -m "test: remove legacy target world message contract"
```

### Task 5: Run contract regression and update the approved spec only if needed

**Files:**
- Modify: `docs/superpowers/specs/2026-04-25-outward-message-contract-design.md` (only if implementation reveals a contradiction)

- [ ] **Step 1: Run the contract-focused test suite**

Run:

```bash
pytest \
  tests/runtime/messaging/test_envelope.py \
  tests/runtime/messaging/test_sqlite_store.py \
  tests/runtime/messaging/test_world_sender.py \
  tests/runtime/messaging/test_inbox_processor.py \
  tests/runtime/messaging/test_world_ingress.py \
  tests/runtime/test_instance_manager.py \
  tests/runtime/test_message_hub.py \
  tests/worker/test_manager.py -v
```

Expected: PASS

- [ ] **Step 2: Run one broader runtime/worker sanity pass**

Run:

```bash
pytest tests/runtime/test_event_bus.py tests/runtime/test_world_registry.py tests/worker/cli/test_run_command.py tests/worker/cli/test_run_inline.py -v
```

Expected: PASS

- [ ] **Step 3: If implementation contradicted the spec, update the spec inline**

Only make this change if needed. The only acceptable diff shape is a clarification like:

```markdown
- `headers` 必须是 `dict[str, str]`。
- `headers` 必须是 `dict[str, str]`；非字符串值在 action 校验阶段直接报错，不做隐式转换。
```

- [ ] **Step 4: Commit any doc clarification**

```bash
git add docs/superpowers/specs/2026-04-25-outward-message-contract-design.md
git commit -m "docs: clarify outward message contract validation"
```

Skip this commit if no doc change was needed.

## Self-Review

### Spec coverage

- Section 5 (`MessageEnvelope` contract) -> Task 1
- Section 6 (outbound/inbound/world-internal routing) -> Tasks 2 and 3
- Section 7 (`triggerEvent external=true` contract) -> Tasks 2 and 4
- Section 8 (code migration points) -> Tasks 1 through 4
- Section 9 (storage migration and outbox source/target reversal) -> Task 1
- Section 10 (test requirements, including `source_world` retention) -> Tasks 3 and 5
- Section 11 (direct deletion of `targetWorldId`) -> Task 4

No uncovered spec sections remain.

### Placeholder scan

- No `TBD`, `TODO`, or deferred implementation wording in task steps.
- Every code-changing step includes a concrete snippet or concrete diff target.
- Every verification step includes exact commands and expected outcomes.

### Type consistency

- Top-level envelope fields consistently use `source_world` / `target_world`.
- World-internal route field consistently remains `target`.
- Outward publish signatures no longer mention `target_world_id`.
- Action validation consistently rejects `targetWorldId`.
