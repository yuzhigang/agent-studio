import pytest

from src.runtime.event_bus import EventBus
from src.runtime.message_hub import MessageHub


@pytest.fixture
def msg_store(tmp_path):
    from src.runtime.stores.sqlite_message_store import SQLiteMessageStore

    s = SQLiteMessageStore(str(tmp_path / "worker"))
    yield s
    s.close()


class FakeChannel:
    def __init__(self):
        self.started = False
        self.stopped = False
        self._ready = False
        self.messages = []

    async def start(self, callback):
        self.started = True
        self._callback = callback

    async def stop(self):
        self.stopped = True

    def is_ready(self):
        return self._ready

    async def send(self, event_type, payload, source, scope, target):
        self.messages.append(
            {"event_type": event_type, "payload": payload, "source": source, "scope": scope, "target": target}
        )
        from src.worker.channels.base import SendResult
        return SendResult.SUCCESS


def test_register_project_adds_hook_and_writes_outbox(msg_store):
    hub = MessageHub(msg_store, channel=None)
    bus = EventBus()
    model_events = {"order.created": {"external": True}}

    hub.register_project("proj-1", bus, model_events)

    bus.publish("order.created", {"id": "123"}, "src-1", "project")

    pending = msg_store.outbox_read_pending(limit=10)
    assert len(pending) == 1
    assert pending[0]["event_type"] == "order.created"
    assert pending[0]["payload"] == {"id": "123"}
    assert pending[0]["source"] == "src-1"


def test_unregister_project_removes_hook(msg_store):
    hub = MessageHub(msg_store, channel=None)
    bus = EventBus()
    model_events = {"order.created": {"external": True}}

    hub.register_project("proj-1", bus, model_events)
    hub.unregister_project("proj-1")

    bus.publish("order.created", {"id": "123"}, "src-1", "project")

    pending = msg_store.outbox_read_pending(limit=10)
    assert len(pending) == 0


def test_non_external_event_does_not_write_outbox(msg_store):
    hub = MessageHub(msg_store, channel=None)
    bus = EventBus()
    model_events = {"order.created": {"external": True}, "internal.tick": {"external": False}}

    hub.register_project("proj-1", bus, model_events)

    bus.publish("internal.tick", {"step": 1}, "src-1", "project")

    pending = msg_store.outbox_read_pending(limit=10)
    assert len(pending) == 0


def test_on_channel_message_writes_inbox(msg_store):
    hub = MessageHub(msg_store, channel=None)

    hub.on_channel_message("notify.alert", {"level": "high"}, "ext-1", "project", "tgt-1")

    pending = msg_store.inbox_read_pending(limit=10)
    assert len(pending) == 1
    assert pending[0]["event_type"] == "notify.alert"
    assert pending[0]["payload"] == {"level": "high"}
    assert pending[0]["source"] == "ext-1"
    assert pending[0]["scope"] == "project"
    assert pending[0]["target"] == "tgt-1"


@pytest.mark.anyio(backend="asyncio")
async def test_start_stop_manages_processors_and_channel(msg_store):
    channel = FakeChannel()
    hub = MessageHub(msg_store, channel=channel)

    await hub.start()
    assert channel.started is True
    assert hub._inbox_processor is not None
    assert hub._outbox_processor is not None

    await hub.stop()
    assert channel.stopped is True
    assert hub._inbox_processor is None
    assert hub._outbox_processor is None


def test_is_ready_without_channel():
    hub = MessageHub(message_store=None, channel=None)
    assert hub.is_ready() is True


def test_is_ready_with_channel():
    channel = FakeChannel()
    hub = MessageHub(message_store=None, channel=channel)
    assert hub.is_ready() is False
    channel._ready = True
    assert hub.is_ready() is True


def test_register_project_idempotent(msg_store):
    hub = MessageHub(msg_store, channel=None)
    bus = EventBus()
    model_events = {"order.created": {"external": True}}

    hub.register_project("proj-1", bus, model_events)
    hub.register_project("proj-1", bus, model_events)

    assert len(hub.registered_projects()) == 1

    bus.publish("order.created", {"id": "123"}, "src-1", "project")
    pending = msg_store.outbox_read_pending(limit=10)
    assert len(pending) == 1


def test_publish_does_not_trigger_pre_publish_hook(msg_store):
    bus = EventBus()
    hub = MessageHub(msg_store, None)
    hub.register_project("proj-01", bus, {"order.created": {"external": True}})

    hub.publish("order.created", {"id": "123"}, "src-1", "project")

    # publish() should NOT write to outbox
    pending = msg_store.outbox_read_pending(10)
    assert len(pending) == 0


def test_publish_respects_target(msg_store):
    bus = EventBus()
    hub = MessageHub(msg_store, None)
    hub.register_project("proj-01", bus, {"evt": {"external": True}})

    received_target = []
    received_other = []
    bus.register("inst-target", "project", "evt", lambda t, p, s: received_target.append(t))
    bus.register("inst-other", "project", "evt", lambda t, p, s: received_other.append(t))

    # target in EventBus is instance_id, not project_id
    hub.publish("evt", {"val": 1}, "src", "project", target="inst-target")

    assert len(received_target) == 1
    assert len(received_other) == 0
