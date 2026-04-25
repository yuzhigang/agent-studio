import asyncio

import pytest

from src.runtime.messaging import (
    MessageEnvelope,
    MessageHub,
    PermanentDeliveryError,
    RetryableDeliveryError,
)
from src.runtime.messaging.sqlite_store import SQLiteMessageStore


@pytest.mark.anyio
async def test_inbox_processor_expands_broadcast_and_delivers(tmp_path):
    store = SQLiteMessageStore(str(tmp_path))
    seen = []
    received = asyncio.Event()

    class _Receiver:
        def __init__(self, world_id):
            self._world_id = world_id

        async def receive(self, envelope):
            seen.append((self._world_id, envelope.message_id))
            if len(seen) == 2:
                received.set()

    hub = MessageHub(message_store=store, channel=None, poll_interval=0.01)
    hub.register_world("factory-a", _Receiver("factory-a"))
    hub.register_world("factory-b", _Receiver("factory-b"))
    hub.on_inbound(
        MessageEnvelope(
            message_id="msg-1",
            source_world="erp",
            target_world="*",
            event_type="shift.changed",
            payload={"shift": "night"},
        )
    )

    try:
        await hub.start()
        await asyncio.wait_for(received.wait(), timeout=1.0)
    finally:
        await hub.stop()
        store.close()

    assert sorted(seen) == [("factory-a", "msg-1"), ("factory-b", "msg-1")]


@pytest.mark.anyio
async def test_inbox_processor_marks_retry_for_unavailable_world(tmp_path):
    store = SQLiteMessageStore(str(tmp_path))
    hub = MessageHub(
        message_store=store,
        channel=None,
        poll_interval=0.01,
        max_retries=2,
    )
    hub.on_inbound(
        MessageEnvelope(
            message_id="msg-2",
            source_world="erp",
            target_world="factory-a",
            event_type="order.created",
            payload={"order_id": "O2"},
        )
    )

    try:
        await hub.start()
        await asyncio.sleep(0.05)
    finally:
        await hub.stop()

    row = store._conn.execute(
        "SELECT status, error_count, last_error FROM inbox_deliveries WHERE message_id = ?",
        ("msg-2",),
    ).fetchone()
    store.close()

    assert row == ("retry", 0, "world receiver unavailable")


@pytest.mark.anyio
async def test_inbox_processor_leaves_targetless_messages_pending(tmp_path):
    store = SQLiteMessageStore(str(tmp_path))
    hub = MessageHub(
        message_store=store,
        channel=None,
        poll_interval=0.01,
        max_retries=2,
    )
    hub.on_inbound(
        MessageEnvelope(
            message_id="msg-no-target",
            source_world="erp",
            target_world=None,
            event_type="order.created",
            payload={"order_id": "O-no-target"},
        )
    )

    try:
        await hub.start()
        await asyncio.sleep(0.05)
    finally:
        await hub.stop()

    inbox_row = store._conn.execute(
        "SELECT status, source_world, target_world FROM inbox WHERE message_id = ?",
        ("msg-no-target",),
    ).fetchone()
    delivery_count = store._conn.execute(
        "SELECT COUNT(*) FROM inbox_deliveries WHERE message_id = ?",
        ("msg-no-target",),
    ).fetchone()[0]
    store.close()

    assert inbox_row == ("pending", "erp", None)
    assert delivery_count == 0


@pytest.mark.anyio
async def test_inbox_processor_handles_retryable_and_permanent_errors(tmp_path):
    store = SQLiteMessageStore(str(tmp_path))
    attempts = {"retry": 0, "dead": 0}
    retry_event = asyncio.Event()
    dead_event = asyncio.Event()

    class _RetryReceiver:
        async def receive(self, envelope):
            attempts["retry"] += 1
            retry_event.set()
            raise RetryableDeliveryError("temporary")

    class _DeadReceiver:
        async def receive(self, envelope):
            attempts["dead"] += 1
            dead_event.set()
            raise PermanentDeliveryError("rejected")

    hub = MessageHub(
        message_store=store,
        channel=None,
        poll_interval=0.01,
        max_retries=2,
    )
    hub.register_world("factory-a", _RetryReceiver())
    hub.register_world("factory-b", _DeadReceiver())
    hub.on_inbound(
        MessageEnvelope(
            message_id="msg-3",
            source_world="erp",
            target_world="factory-a",
            event_type="order.created",
            payload={"order_id": "O3"},
        )
    )
    hub.on_inbound(
        MessageEnvelope(
            message_id="msg-4",
            source_world="erp",
            target_world="factory-b",
            event_type="order.created",
            payload={"order_id": "O4"},
        )
    )

    try:
        await hub.start()
        await asyncio.wait_for(retry_event.wait(), timeout=1.0)
        await asyncio.wait_for(dead_event.wait(), timeout=1.0)
    finally:
        await hub.stop()

    retry_row = store._conn.execute(
        "SELECT status, error_count, last_error FROM inbox_deliveries WHERE message_id = ?",
        ("msg-3",),
    ).fetchone()
    dead_row = store._conn.execute(
        "SELECT status, error_count, last_error FROM inbox_deliveries WHERE message_id = ?",
        ("msg-4",),
    ).fetchone()
    store.close()

    assert attempts == {"retry": 1, "dead": 1}
    assert retry_row == ("retry", 1, "temporary")
    assert dead_row == ("dead", 1, "rejected")


@pytest.mark.anyio
async def test_inbox_processor_unexpected_exception_does_not_cancel_other_worlds(tmp_path):
    store = SQLiteMessageStore(str(tmp_path))
    seen = []
    delivered = asyncio.Event()

    class _BoomReceiver:
        async def receive(self, envelope):
            raise RuntimeError("boom")

    class _OkReceiver:
        async def receive(self, envelope):
            seen.append((envelope.source_world, envelope.target_world, envelope.message_id))
            delivered.set()

    hub = MessageHub(
        message_store=store,
        channel=None,
        poll_interval=0.01,
        max_retries=2,
    )
    hub.register_world("factory-a", _BoomReceiver())
    hub.register_world("factory-b", _OkReceiver())
    hub.on_inbound(
        MessageEnvelope(
            message_id="msg-5",
            source_world="erp-a",
            target_world="factory-a",
            event_type="order.created",
            payload={"order_id": "O5"},
        )
    )
    hub.on_inbound(
        MessageEnvelope(
            message_id="msg-6",
            source_world="erp-b",
            target_world="factory-b",
            event_type="order.created",
            payload={"order_id": "O6"},
        )
    )

    try:
        await hub.start()
        await asyncio.wait_for(delivered.wait(), timeout=1.0)
    finally:
        await hub.stop()

    bad_row = store._conn.execute(
        "SELECT status, error_count, last_error FROM inbox_deliveries WHERE message_id = ?",
        ("msg-5",),
    ).fetchone()
    good_row = store._conn.execute(
        "SELECT status FROM inbox_deliveries WHERE message_id = ?",
        ("msg-6",),
    ).fetchone()
    store.close()

    assert seen == [("erp-b", "factory-b", "msg-6")]
    assert bad_row[0] == "retry"
    assert bad_row[1] == 1
    assert "unexpected error: boom" == bad_row[2]
    assert good_row == ("delivered",)


@pytest.mark.anyio
async def test_inbox_processor_missing_inbox_message_does_not_block_same_world_followups(tmp_path):
    store = SQLiteMessageStore(str(tmp_path))
    seen = []
    delivered = asyncio.Event()

    class _Receiver:
        async def receive(self, envelope):
            seen.append(envelope.message_id)
            delivered.set()

    hub = MessageHub(
        message_store=store,
        channel=None,
        poll_interval=0.01,
        max_retries=2,
    )
    hub.register_world("factory-a", _Receiver())

    store.inbox_append(
        MessageEnvelope(
            message_id="msg-missing",
            source_world="erp",
            target_world="factory-a",
            event_type="order.created",
            payload={"order_id": "missing"},
        )
    )
    store.inbox_append(
        MessageEnvelope(
            message_id="msg-good",
            source_world="erp",
            target_world="factory-a",
            event_type="order.created",
            payload={"order_id": "good"},
        )
    )
    store.inbox_create_deliveries("msg-missing", ["factory-a"])
    store.inbox_create_deliveries("msg-good", ["factory-a"])
    store.inbox_mark_expanded("msg-missing")
    store.inbox_mark_expanded("msg-good")

    original_inbox_load = store.inbox_load

    def _broken_inbox_load(message_id: str):
        if message_id == "msg-missing":
            raise KeyError("missing inbox message")
        return original_inbox_load(message_id)

    store.inbox_load = _broken_inbox_load

    try:
        await hub.start()
        await asyncio.wait_for(delivered.wait(), timeout=1.0)
    finally:
        await hub.stop()

    missing_row = store._conn.execute(
        "SELECT status, last_error FROM inbox_deliveries WHERE message_id = ?",
        ("msg-missing",),
    ).fetchone()
    good_row = store._conn.execute(
        "SELECT status FROM inbox_deliveries WHERE message_id = ?",
        ("msg-good",),
    ).fetchone()
    store.close()

    assert seen == ["msg-good"]
    assert missing_row == ("dead", "missing inbox message")
    assert good_row == ("delivered",)


@pytest.mark.anyio
async def test_inbox_handler_failure_is_not_visible_to_processor(tmp_path):
    """EventBus swallows handler exceptions, so WorldMessageIngress.receive()
    returns normally even if an internal handler crashed. InboxProcessor
    therefore marks the delivery as delivered, not retry/dead.
    This documents the current architecture gap: inbox retry does not
    reflect world-internal handler failures.
    """
    store = SQLiteMessageStore(str(tmp_path))
    from src.runtime.event_bus import EventBus
    from src.runtime.world_event_emitter import WorldEventEmitter
    from src.runtime.messaging.world_ingress import WorldMessageIngress

    bus = EventBus()
    received = asyncio.Event()

    def _failing_handler(event_type, payload, source):
        received.set()
        raise RuntimeError("handler crashed internally")

    bus.register("inst-1", "world", "order.created", _failing_handler)

    emitter = WorldEventEmitter(bus)
    ingress = WorldMessageIngress(emitter)

    hub = MessageHub(
        message_store=store,
        channel=None,
        poll_interval=0.01,
        max_retries=2,
    )
    hub.register_world("factory-a", ingress)
    hub.on_inbound(
        MessageEnvelope(
            message_id="msg-handler-boom",
            source_world="erp",
            target_world="factory-a",
            event_type="order.created",
            payload={"order_id": "boom"},
        )
    )

    try:
        await hub.start()
        await asyncio.wait_for(received.wait(), timeout=1.0)
        await asyncio.sleep(0.05)
    finally:
        await hub.stop()

    row = store._conn.execute(
        "SELECT status, error_count FROM inbox_deliveries WHERE message_id = ?",
        ("msg-handler-boom",),
    ).fetchone()
    store.close()

    # Because WorldMessageIngress passes raise_on_error=True, the handler
    # exception propagates to InboxProcessor and is treated as retryable.
    assert row[0] == "retry"
    assert row[1] == 1


@pytest.mark.anyio
async def test_inbox_delivery_resumes_after_world_re_registration(tmp_path):
    """When a world is unregistered (non-permanent) and later re-registered,
    pending deliveries should be retried and eventually delivered.
    """
    store = SQLiteMessageStore(str(tmp_path))
    seen = []
    delivered = asyncio.Event()

    class _Receiver:
        async def receive(self, envelope):
            seen.append(envelope.message_id)
            delivered.set()

    hub = MessageHub(
        message_store=store,
        channel=None,
        poll_interval=0.01,
        max_retries=3,
    )
    hub.on_inbound(
        MessageEnvelope(
            message_id="msg-backlog",
            source_world="erp",
            target_world="factory-a",
            event_type="order.created",
            payload={"order_id": "backlog"},
        )
    )

    try:
        await hub.start()
        # Wait for the delivery to hit retry because receiver is missing
        await asyncio.sleep(0.05)
        # Manually set retry_after to the past so the next poll picks it up
        store._conn.execute(
            """
            UPDATE inbox_deliveries
            SET retry_after = '2000-01-01T00:00:00+00:00'
            WHERE message_id = ?
            """,
            ("msg-backlog",),
        )
        store._conn.commit()
        # Now register the world
        hub.register_world("factory-a", _Receiver())
        await asyncio.wait_for(delivered.wait(), timeout=1.0)
        # Give reconcile a chance to run before checking status
        await asyncio.sleep(0.05)
    finally:
        await hub.stop()

    row = store._conn.execute(
        "SELECT status FROM inbox_deliveries WHERE message_id = ?",
        ("msg-backlog",),
    ).fetchone()
    inbox_row = store._conn.execute(
        "SELECT status FROM inbox WHERE message_id = ?",
        ("msg-backlog",),
    ).fetchone()
    store.close()

    assert row == ("delivered",)
    assert inbox_row == ("completed",)
    assert seen == ["msg-backlog"]
