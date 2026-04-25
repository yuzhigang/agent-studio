import asyncio

import pytest

from src.runtime.messaging import MessageEnvelope, MessageHub, SendResult
from src.runtime.messaging.sqlite_store import SQLiteMessageStore


class _FakeChannel:
    def __init__(self, result=SendResult.SUCCESS):
        self._result = result
        self.sent = []
        self.sent_event = asyncio.Event()
        self.callback = None

    async def start(self, inbound_callback):
        self.callback = inbound_callback

    async def send(self, envelope):
        self.sent.append(envelope.message_id)
        self.sent_event.set()
        return self._result

    async def stop(self):
        return None

    def is_ready(self):
        return True


@pytest.mark.anyio
async def test_outbox_processor_sends_enqueued_envelope(tmp_path):
    store = SQLiteMessageStore(str(tmp_path))
    channel = _FakeChannel()
    hub = MessageHub(message_store=store, channel=channel, poll_interval=0.01)
    hub.enqueue_outbound(
        MessageEnvelope(
            message_id="msg-9",
            world_id="factory-b",
            event_type="order.created",
            payload={"order_id": "O9"},
        )
    )

    try:
        await hub.start()
        await asyncio.wait_for(channel.sent_event.wait(), timeout=1.0)
    finally:
        await hub.stop()

    row = store._conn.execute(
        "SELECT status FROM outbox WHERE message_id = ?",
        ("msg-9",),
    ).fetchone()
    store.close()

    assert channel.sent == ["msg-9"]
    assert row == ("sent",)


@pytest.mark.anyio
async def test_outbox_processor_marks_retryable_send_for_retry(tmp_path):
    store = SQLiteMessageStore(str(tmp_path))
    channel = _FakeChannel(result=SendResult.RETRYABLE)
    hub = MessageHub(
        message_store=store,
        channel=channel,
        poll_interval=0.01,
        max_retries=3,
    )
    hub.enqueue_outbound(
        MessageEnvelope(
            message_id="msg-10",
            world_id="factory-b",
            event_type="order.created",
            payload={"order_id": "O10"},
        )
    )

    try:
        await hub.start()
        await asyncio.wait_for(channel.sent_event.wait(), timeout=1.0)
    finally:
        await hub.stop()

    row = store._conn.execute(
        "SELECT status, error_count, last_error FROM outbox WHERE message_id = ?",
        ("msg-10",),
    ).fetchone()
    store.close()

    assert channel.sent == ["msg-10"]
    assert row == ("retry", 1, "retryable failure")


@pytest.mark.anyio
async def test_outbox_processor_marks_permanent_send_dead(tmp_path):
    store = SQLiteMessageStore(str(tmp_path))
    channel = _FakeChannel(result=SendResult.PERMANENT)
    hub = MessageHub(
        message_store=store,
        channel=channel,
        poll_interval=0.01,
        max_retries=3,
    )
    hub.enqueue_outbound(
        MessageEnvelope(
            message_id="msg-11",
            world_id="factory-b",
            event_type="order.created",
            payload={"order_id": "O11"},
        )
    )

    try:
        await hub.start()
        await asyncio.wait_for(channel.sent_event.wait(), timeout=1.0)
    finally:
        await hub.stop()

    row = store._conn.execute(
        "SELECT status, error_count, last_error FROM outbox WHERE message_id = ?",
        ("msg-11",),
    ).fetchone()
    store.close()

    assert channel.sent == ["msg-11"]
    assert row == ("dead", 3, "permanent failure")
