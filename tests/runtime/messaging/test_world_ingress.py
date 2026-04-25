import asyncio

import pytest

from src.runtime.event_bus import EventBus
from src.runtime.messaging import MessageEnvelope, WorldEventEmitter, WorldMessageIngress


@pytest.mark.anyio
async def test_eventbus_message_adapter_publishes_to_event_bus():
    bus = EventBus()
    seen = []
    event = asyncio.Event()

    bus.register(
        "inst-1",
        "world",
        "order.created",
        lambda event_type, payload, source: (
            seen.append((event_type, payload, source)),
            event.set(),
        ),
    )

    adapter = WorldMessageIngress(WorldEventEmitter(bus))
    await adapter.receive(
        MessageEnvelope(
            message_id="msg-1",
            world_id="factory-a",
            event_type="order.created",
            payload={"order_id": "O1001"},
            source="erp",
        )
    )

    await asyncio.wait_for(event.wait(), timeout=1.0)
    assert seen == [("order.created", {"order_id": "O1001"}, "erp")]


@pytest.mark.anyio
async def test_world_ingress_uses_same_task_context_as_caller():
    class _Emitter:
        def __init__(self):
            self.task_ids = []

        def publish_internal(self, **kwargs):
            self.task_ids.append(id(asyncio.current_task()))

    emitter = _Emitter()
    adapter = WorldMessageIngress(emitter)
    caller_task_id = id(asyncio.current_task())

    await adapter.receive(
        MessageEnvelope(
            message_id="msg-2",
            world_id="factory-a",
            event_type="order.created",
            payload={"order_id": "O1002"},
            source="erp",
        )
    )

    assert emitter.task_ids == [caller_task_id]
