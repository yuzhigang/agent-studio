from src.runtime.messaging import MessageEnvelope, WorldMessageSender


class _FakeHub:
    def __init__(self):
        self.seen = []

    def enqueue_outbound(self, envelope: MessageEnvelope) -> None:
        self.seen.append(envelope)


def test_world_message_sender_builds_envelope_and_enqueues():
    hub = _FakeHub()
    sender = WorldMessageSender(world_id="factory-a", hub=hub, source="world:factory-a")

    message_id = sender.send(
        "order.created",
        {"order_id": "O1001"},
        target="robot-7",
        trace_id="trace-9",
        headers={"priority": "high"},
    )

    assert message_id
    assert len(hub.seen) == 1
    assert hub.seen[0].source_world == "factory-a"
    assert hub.seen[0].target_world is None
    assert hub.seen[0].source == "world:factory-a"
    assert hub.seen[0].target == "robot-7"


def test_world_message_sender_can_bind_hub_after_creation():
    hub = _FakeHub()
    sender = WorldMessageSender(world_id="factory-a", hub=None, source="world:factory-a")

    sender.bind_hub(hub)
    sender.send("order.created", {"order_id": "O1001"})

    assert len(hub.seen) == 1
    assert hub.seen[0].source_world == "factory-a"
    assert hub.seen[0].target_world is None
