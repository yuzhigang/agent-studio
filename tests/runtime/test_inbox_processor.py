import asyncio

import pytest

from src.runtime.event_bus import EventBus
from src.runtime.message_hub import MessageHub
from src.runtime.stores.sqlite_message_store import SQLiteMessageStore


@pytest.fixture
def msg_store(tmp_path):
    s = SQLiteMessageStore(str(tmp_path / "worker"))
    try:
        yield s
    finally:
        s.close()


@pytest.mark.anyio(backend="asyncio")
async def test_inbox_processor_injects_events_into_event_bus(msg_store):
    bus = EventBus()
    received = []
    event = asyncio.Event()
    bus.register(
        "inst-1",
        "project",
        "order.created",
        lambda t, p, s: (received.append((t, p, s)), event.set()),
    )

    hub = MessageHub(msg_store, channel=None)
    hub.register_project("proj-1", bus, {"order.created": {"external": True}})

    msg_store.inbox_enqueue("order.created", {"id": "123"}, "ext-1", "project", None)

    await hub.start()
    try:
        await asyncio.wait_for(event.wait(), timeout=2.0)
    finally:
        await hub.stop()

    assert len(received) == 1
    assert received[0] == ("order.created", {"id": "123"}, "ext-1")

    pending = msg_store.inbox_read_pending(limit=10)
    assert len(pending) == 0


@pytest.mark.anyio(backend="asyncio")
async def test_inbox_processor_no_outbox_loop(msg_store):
    bus = EventBus()
    received = []
    event = asyncio.Event()
    bus.register(
        "inst-1",
        "project",
        "order.created",
        lambda t, p, s: (received.append((t, p, s)), event.set()),
    )

    hub = MessageHub(msg_store, channel=None)
    hub.register_project("proj-1", bus, {"order.created": {"external": True}})

    msg_store.inbox_enqueue("order.created", {"id": "456"}, "ext-1", "project", None)

    await hub.start()
    try:
        await asyncio.wait_for(event.wait(), timeout=2.0)
    finally:
        await hub.stop()

    assert len(received) == 1

    outbox = msg_store.outbox_read_pending(limit=10)
    assert len(outbox) == 0


@pytest.mark.anyio(backend="asyncio")
async def test_inbox_processor_target_routing(msg_store):
    bus = EventBus()
    received_target = []
    received_other = []
    event = asyncio.Event()
    bus.register(
        "inst-target",
        "project",
        "notify.alert",
        lambda t, p, s: (received_target.append((t, p, s)), event.set()),
    )
    bus.register(
        "inst-other",
        "project",
        "notify.alert",
        lambda t, p, s: received_other.append((t, p, s)),
    )

    hub = MessageHub(msg_store, channel=None)
    hub.register_project("proj-1", bus, {"notify.alert": {"external": True}})

    msg_store.inbox_enqueue(
        "notify.alert", {"level": "high"}, "ext-1", "project", "inst-target"
    )

    await hub.start()
    try:
        await asyncio.wait_for(event.wait(), timeout=2.0)
    finally:
        await hub.stop()

    assert len(received_target) == 1
    assert received_target[0] == ("notify.alert", {"level": "high"}, "ext-1")
    assert len(received_other) == 0
