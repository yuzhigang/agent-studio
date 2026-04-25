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
            world_id="*",
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
            world_id="factory-a",
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
            world_id="factory-a",
            event_type="order.created",
            payload={"order_id": "O3"},
        )
    )
    hub.on_inbound(
        MessageEnvelope(
            message_id="msg-4",
            world_id="factory-b",
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
            seen.append((envelope.world_id, envelope.message_id))
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
            world_id="factory-a",
            event_type="order.created",
            payload={"order_id": "O5"},
        )
    )
    hub.on_inbound(
        MessageEnvelope(
            message_id="msg-6",
            world_id="factory-b",
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

    assert seen == [("factory-b", "msg-6")]
    assert bad_row[0] == "retry"
    assert bad_row[1] == 1
    assert "unexpected error: boom" == bad_row[2]
    assert good_row == ("delivered",)
