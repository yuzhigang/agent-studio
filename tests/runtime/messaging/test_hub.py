import asyncio

import pytest

from src.runtime.messaging import MessageEnvelope, MessageHub
from src.runtime.messaging.sqlite_store import SQLiteMessageStore


def test_hub_registers_and_unregisters_world(tmp_path):
    store = SQLiteMessageStore(str(tmp_path))
    try:
        hub = MessageHub(message_store=store, channel=None)

        class _Receiver:
            async def receive(self, envelope):
                raise AssertionError("should not be called")

        hub.register_world("factory-a", _Receiver())
        assert set(hub.registered_worlds()) == {"factory-a"}

        hub.unregister_world("factory-a")
        assert hub.registered_worlds() == []
    finally:
        store.close()


def test_hub_unregister_world_permanent_marks_pending_deliveries_dead(tmp_path):
    store = SQLiteMessageStore(str(tmp_path))
    try:
        hub = MessageHub(message_store=store, channel=None)
        hub.on_inbound(
            MessageEnvelope(
                message_id="msg-1",
                world_id="factory-a",
                event_type="order.created",
                payload={"order_id": "O1001"},
            )
        )
        store.inbox_create_deliveries("msg-1", ["factory-a"])
        store.inbox_mark_expanded("msg-1")

        hub.unregister_world("factory-a", permanent=True)

        row = store._conn.execute(
            "SELECT status, last_error FROM inbox_deliveries WHERE message_id = ? AND target_world_id = ?",
            ("msg-1", "factory-a"),
        ).fetchone()
        assert row == ("dead", "world permanently removed")
    finally:
        store.close()


@pytest.mark.anyio
async def test_hub_starts_and_stops_processors_and_channel(tmp_path):
    store = SQLiteMessageStore(str(tmp_path))

    class _Channel:
        def __init__(self):
            self.started = False
            self.stopped = False
            self.callback = None

        async def start(self, inbound_callback):
            self.started = True
            self.callback = inbound_callback

        async def stop(self):
            self.stopped = True

        async def send(self, envelope):
            return None

        def is_ready(self):
            return True

    channel = _Channel()
    hub = MessageHub(message_store=store, channel=channel, poll_interval=0.01)

    try:
        await hub.start()
        assert channel.started is True
        assert callable(channel.callback)
        assert hub._inbox_processor is not None
        assert hub._outbox_processor is not None

        hub.on_inbound(
            MessageEnvelope(
                message_id="msg-1",
                world_id="factory-a",
                event_type="order.created",
                payload={"order_id": "O1001"},
            )
        )
        await asyncio.sleep(0.02)
    finally:
        await hub.stop()
        store.close()

    assert channel.stopped is True


def test_hub_is_ready_without_channel():
    hub = MessageHub(message_store=None, channel=None)
    assert hub.is_ready() is True
