import asyncio

import pytest

from src.runtime.message_hub import MessageHub
from src.runtime.stores.sqlite_message_store import SQLiteMessageStore
from src.worker.channels.base import SendResult

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
        self.messages = []
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

    async def send(self, event_type, payload, source, scope, target):
        self.messages.append(
            {"event_type": event_type, "payload": payload, "source": source, "scope": scope, "target": target}
        )
        self.sent_event.set()
        return self.result


async def test_outbox_processor_sends_and_marks_sent(msg_store):
    channel = FakeChannel(result=SendResult.SUCCESS)
    hub = MessageHub(msg_store, channel=channel)

    msg_store.outbox_enqueue("order.created", {"id": "123"}, "src-1", "project", None)

    await hub.start()
    try:
        assert channel.started is True
        await asyncio.wait_for(channel.sent_event.wait(), timeout=2.0)
    finally:
        await hub.stop()

    assert len(channel.messages) == 1
    assert channel.messages[0]["event_type"] == "order.created"

    pending = msg_store.outbox_read_pending(limit=10)
    assert len(pending) == 0

    row = msg_store._conn.execute(
        "SELECT published_at FROM outbox WHERE event_type = ?", ("order.created",)
    ).fetchone()
    assert row is not None
    assert row[0] is not None


async def test_outbox_processor_retries_on_retryable(msg_store):
    channel = FakeChannel(result=SendResult.RETRYABLE)
    hub = MessageHub(msg_store, channel=channel)

    msg_store.outbox_enqueue("order.created", {"id": "456"}, "src-1", "project", None)

    await hub.start()
    try:
        await asyncio.wait_for(channel.sent_event.wait(), timeout=2.0)
    finally:
        await hub.stop()

    assert len(channel.messages) == 1

    pending = msg_store.outbox_read_pending(limit=10)
    assert len(pending) == 0

    row = msg_store._conn.execute(
        "SELECT error_count, retry_after, last_error FROM outbox WHERE event_type = ?",
        ("order.created",),
    ).fetchone()
    assert row is not None
    error_count, retry_after, last_error = row
    assert error_count == 1
    assert retry_after is not None
    assert last_error == "retryable failure"


async def test_outbox_processor_permanent_failure(msg_store):
    channel = FakeChannel(result=SendResult.PERMANENT)
    hub = MessageHub(msg_store, channel=channel)

    msg_store.outbox_enqueue("order.created", {"id": "789"}, "src-1", "project", None)

    await hub.start()
    try:
        await asyncio.wait_for(channel.sent_event.wait(), timeout=2.0)
    finally:
        await hub.stop()

    assert len(channel.messages) == 1

    pending = msg_store.outbox_read_pending(limit=10)
    assert len(pending) == 0

    row = msg_store._conn.execute(
        "SELECT error_count, retry_after, last_error FROM outbox WHERE event_type = ?",
        ("order.created",),
    ).fetchone()
    assert row is not None
    error_count, retry_after, last_error = row
    assert error_count == 10
    assert retry_after is None
    assert last_error == "permanent failure"


async def test_outbox_processor_no_channel_does_not_crash(msg_store):
    hub = MessageHub(msg_store, channel=None)

    msg_store.outbox_enqueue("order.created", {"id": "000"}, "src-1", "project", None)

    await hub.start()
    try:
        await asyncio.sleep(0.2)
    finally:
        await hub.stop()

    pending = msg_store.outbox_read_pending(limit=10)
    assert len(pending) == 1
    assert pending[0]["payload"] == {"id": "000"}
