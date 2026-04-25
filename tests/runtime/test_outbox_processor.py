import asyncio

import pytest

from src.runtime.messaging import MessageEnvelope, MessageHub, SendResult
from src.runtime.messaging.sqlite_store import SQLiteMessageStore

pytestmark = pytest.mark.anyio(backend="asyncio")


@pytest.fixture
def msg_store(tmp_path):
    s = SQLiteMessageStore(str(tmp_path / "worker"))
    try:
        yield s
    finally:
        s.close()


class FakeChannel:
    def __init__(self, result=SendResult.SUCCESS):
        self.result = result
        self.messages: list[MessageEnvelope] = []
        self.started = False
        self.stopped = False
        self._ready = True
        self.sent_event = asyncio.Event()

    async def start(self, callback):
        self.started = True

    async def stop(self):
        self.stopped = True

    def is_ready(self):
        return self._ready

    async def send(self, envelope):
        self.messages.append(envelope)
        self.sent_event.set()
        return self.result


async def test_outbox_processor_sends_and_marks_sent(msg_store):
    channel = FakeChannel(result=SendResult.SUCCESS)
    hub = MessageHub(msg_store, channel=channel)

    msg_store.outbox_append(
        MessageEnvelope(
            message_id="msg-success",
            world_id="world-2",
            event_type="order.created",
            payload={"id": "123"},
            source="src-1",
        )
    )

    await hub.start()
    try:
        assert channel.started is True
        await asyncio.wait_for(channel.sent_event.wait(), timeout=2.0)
    finally:
        await hub.stop()

    assert len(channel.messages) == 1
    assert channel.messages[0].event_type == "order.created"

    pending = msg_store.outbox_read_pending(limit=10)
    assert len(pending) == 0

    row = msg_store._conn.execute(
        "SELECT status, sent_at FROM outbox WHERE message_id = ?",
        ("msg-success",),
    ).fetchone()
    assert row == ("sent", row[1])
    assert row[1] is not None


async def test_outbox_processor_retries_on_retryable(msg_store):
    channel = FakeChannel(result=SendResult.RETRYABLE)
    hub = MessageHub(msg_store, channel=channel)

    msg_store.outbox_append(
        MessageEnvelope(
            message_id="msg-retry",
            world_id="world-2",
            event_type="order.created",
            payload={"id": "456"},
            source="src-1",
        )
    )

    await hub.start()
    try:
        await asyncio.wait_for(channel.sent_event.wait(), timeout=2.0)
    finally:
        await hub.stop()

    assert len(channel.messages) == 1

    pending = msg_store.outbox_read_pending(limit=10)
    assert len(pending) == 0

    row = msg_store._conn.execute(
        "SELECT status, error_count, retry_after, last_error FROM outbox WHERE message_id = ?",
        ("msg-retry",),
    ).fetchone()
    assert row is not None
    status, error_count, retry_after, last_error = row
    assert status == "retry"
    assert error_count == 1
    assert retry_after is not None
    assert last_error == "retryable failure"


async def test_outbox_processor_permanent_failure(msg_store):
    channel = FakeChannel(result=SendResult.PERMANENT)
    hub = MessageHub(msg_store, channel=channel)

    msg_store.outbox_append(
        MessageEnvelope(
            message_id="msg-dead",
            world_id="world-2",
            event_type="order.created",
            payload={"id": "789"},
            source="src-1",
        )
    )

    await hub.start()
    try:
        await asyncio.wait_for(channel.sent_event.wait(), timeout=2.0)
    finally:
        await hub.stop()

    assert len(channel.messages) == 1

    pending = msg_store.outbox_read_pending(limit=10)
    assert len(pending) == 0

    row = msg_store._conn.execute(
        "SELECT status, error_count, retry_after, last_error FROM outbox WHERE message_id = ?",
        ("msg-dead",),
    ).fetchone()
    assert row is not None
    status, error_count, retry_after, last_error = row
    assert status == "dead"
    assert error_count == 10
    assert retry_after is None
    assert last_error == "permanent failure"


async def test_outbox_processor_no_channel_does_not_crash(msg_store):
    hub = MessageHub(msg_store, channel=None)

    msg_store.outbox_append(
        MessageEnvelope(
            message_id="msg-pending",
            world_id="world-2",
            event_type="order.created",
            payload={"id": "000"},
            source="src-1",
        )
    )

    await hub.start()
    try:
        await asyncio.sleep(0.2)
    finally:
        await hub.stop()

    pending = msg_store.outbox_read_pending(limit=10)
    assert len(pending) == 1
    assert pending[0].payload == {"id": "000"}
