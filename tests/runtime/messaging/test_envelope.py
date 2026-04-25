from src.runtime.messaging.envelope import MessageEnvelope


def test_message_envelope_round_trips_dict_shape():
    envelope = MessageEnvelope(
        message_id="msg-1",
        world_id="factory-a",
        event_type="order.created",
        payload={"order_id": "O1001"},
        source="erp",
        scope="world",
        target=None,
        trace_id="trace-1",
        headers={"x-env": "test"},
    )

    assert envelope.message_id == "msg-1"
    assert envelope.world_id == "factory-a"
    assert envelope.source == "erp"
    assert envelope.headers == {"x-env": "test"}


def test_message_envelope_allows_explicit_broadcast_world():
    envelope = MessageEnvelope(
        message_id="msg-2",
        world_id="*",
        event_type="shift.changed",
        payload={"shift": "night"},
    )

    assert envelope.world_id == "*"
    assert envelope.scope == "world"
    assert envelope.target is None
