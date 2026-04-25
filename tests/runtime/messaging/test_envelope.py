from src.runtime.messaging.envelope import MessageEnvelope


def test_message_envelope_round_trips_dict_shape():
    envelope = MessageEnvelope(
        message_id="msg-1",
        source_world="factory-a",
        target_world="factory-b",
        event_type="order.created",
        payload={"order_id": "O1001"},
        source="erp",
        scope="world",
        target="ladle-001",
        trace_id="trace-1",
        headers={"x-env": "test"},
    )

    assert envelope.message_id == "msg-1"
    assert envelope.source_world == "factory-a"
    assert envelope.target_world == "factory-b"
    assert envelope.source == "erp"
    assert envelope.target == "ladle-001"
    assert envelope.headers == {"x-env": "test"}


def test_message_envelope_allows_explicit_target_world_broadcast():
    envelope = MessageEnvelope(
        message_id="msg-2",
        source_world="factory-a",
        target_world="*",
        event_type="shift.changed",
        payload={"shift": "night"},
    )

    assert envelope.source_world == "factory-a"
    assert envelope.target_world == "*"
    assert envelope.scope == "world"
    assert envelope.target is None
