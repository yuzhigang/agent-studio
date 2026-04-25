import pytest

from src.runtime.event_bus import EventBus
from src.runtime.messaging import MessageEnvelope, MessageHub, WorldEventEmitter, WorldMessageIngress
from src.runtime.messaging.sqlite_store import SQLiteMessageStore


@pytest.fixture
def msg_store(tmp_path):
    store = SQLiteMessageStore(str(tmp_path / "worker"))
    try:
        yield store
    finally:
        store.close()


class FakeChannel:
    def __init__(self):
        self.started = False
        self.stopped = False
        self._ready = False
        self.messages = []
        self.callback = None

    async def start(self, callback):
        self.started = True
        self.callback = callback

    async def stop(self):
        self.stopped = True

    def is_ready(self):
        return self._ready

    async def send(self, envelope):
        self.messages.append(envelope)
        return None


def test_register_world_tracks_receiver_without_event_bus_hook(msg_store):
    hub = MessageHub(msg_store, channel=None)
    bus = EventBus()

    hub.register_world("world-1", WorldMessageIngress(WorldEventEmitter(bus)))

    bus.publish("order.created", {"id": "123"}, "src-1", "world")

    pending = msg_store.outbox_read_pending(limit=10)
    assert hub.registered_worlds() == ["world-1"]
    assert pending == []


def test_on_inbound_writes_inbox_envelope(msg_store):
    hub = MessageHub(msg_store, channel=None)
    envelope = MessageEnvelope(
        message_id="msg-1",
        source_world="external-world",
        target_world="world-1",
        event_type="notify.alert",
        payload={"level": "high"},
        source="ext-1",
        target="inst-1",
    )

    hub.on_inbound(envelope)

    pending = msg_store.inbox_read_pending(limit=10)
    assert len(pending) == 1
    assert pending[0] == envelope


@pytest.mark.anyio(backend="asyncio")
async def test_start_stop_manages_processors_and_channel(msg_store):
    channel = FakeChannel()
    hub = MessageHub(msg_store, channel=channel, poll_interval=0.01)

    await hub.start()
    assert channel.started is True
    assert callable(channel.callback)
    assert hub._inbox_processor is not None
    assert hub._outbox_processor is not None

    await hub.stop()
    assert channel.stopped is True
    assert hub._inbox_processor is not None
    assert hub._outbox_processor is not None


@pytest.mark.anyio(backend="asyncio")
async def test_stopping_one_world_does_not_stop_shared_message_hub(msg_store):
    hub = MessageHub(msg_store, channel=None, poll_interval=0.01)

    class _Receiver:
        async def receive(self, envelope):
            return None

    hub.register_world("factory-a", _Receiver())
    hub.register_world("factory-b", _Receiver())

    await hub.start()
    hub.unregister_world("factory-a")

    assert hub.registered_worlds() == ["factory-b"]

    await hub.stop()


def test_is_ready_with_and_without_channel(msg_store):
    hub_without_channel = MessageHub(message_store=None, channel=None)
    assert hub_without_channel.is_ready() is True

    channel = FakeChannel()
    hub_with_channel = MessageHub(message_store=msg_store, channel=channel)
    assert hub_with_channel.is_ready() is False
    channel._ready = True
    assert hub_with_channel.is_ready() is True
