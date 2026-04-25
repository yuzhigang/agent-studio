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
            source_world="erp-world",
            target_world="factory-a",
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
            source_world="erp-world",
            target_world="factory-a",
            event_type="order.created",
            payload={"order_id": "O1002"},
            source="erp",
        )
    )

    assert emitter.task_ids == [caller_task_id]


@pytest.mark.anyio
async def test_world_ingress_uses_strict_internal_delivery():
    class _Emitter:
        def __init__(self):
            self.calls = []

        def publish_internal(self, **kwargs):
            self.calls.append(kwargs)
            raise RuntimeError("boom")

    emitter = _Emitter()
    adapter = WorldMessageIngress(emitter)

    with pytest.raises(RuntimeError, match="boom"):
        await adapter.receive(
            MessageEnvelope(
                message_id="msg-3",
                source_world="erp-world",
                target_world="factory-a",
                event_type="order.created",
                payload={"order_id": "O1003"},
                source="erp",
            )
        )

    assert emitter.calls == [
        {
            "event_type": "order.created",
            "payload": {"order_id": "O1003"},
            "source": "erp",
            "scope": "world",
            "target": None,
            "raise_on_error": True,
        }
    ]


@pytest.mark.anyio
async def test_world_ingress_preserves_source_world_on_envelope():
    class _Emitter:
        def publish_internal(self, **kwargs):
            return None

    envelope = MessageEnvelope(
        message_id="msg-4",
        source_world="erp-world",
        target_world="factory-a",
        event_type="order.created",
        payload={"order_id": "O1004"},
        source="erp",
    )

    adapter = WorldMessageIngress(_Emitter())
    await adapter.receive(envelope)

    assert envelope.source_world == "erp-world"
    assert envelope.target_world == "factory-a"
