from src.runtime.messaging import MessageEnvelope
from src.runtime.messaging.sqlite_store import SQLiteMessageStore


def _envelope(message_id: str, world_id: str = "factory-a") -> MessageEnvelope:
    return MessageEnvelope(
        message_id=message_id,
        world_id=world_id,
        event_type="order.created",
        payload={"order_id": message_id},
        source="erp",
    )


def test_inbox_append_and_expand_delivery(tmp_path):
    store = SQLiteMessageStore(str(tmp_path))
    try:
        store.inbox_append(_envelope("msg-1"))
        pending = store.inbox_read_pending(limit=10)
        assert [message.message_id for message in pending] == ["msg-1"]

        store.inbox_create_deliveries("msg-1", ["factory-a"])
        deliveries = store.inbox_read_pending_deliveries(limit=10)
        assert [(delivery.message_id, delivery.target_world_id) for delivery in deliveries] == [
            ("msg-1", "factory-a")
        ]
    finally:
        store.close()


def test_broadcast_delivery_is_unique_per_world(tmp_path):
    store = SQLiteMessageStore(str(tmp_path))
    try:
        store.inbox_append(_envelope("msg-2", world_id="*"))
        store.inbox_create_deliveries("msg-2", ["factory-a", "factory-b"])
        store.inbox_create_deliveries("msg-2", ["factory-a", "factory-b"])

        deliveries = store.inbox_read_pending_deliveries(limit=10)
        assert sorted((delivery.message_id, delivery.target_world_id) for delivery in deliveries) == [
            ("msg-2", "factory-a"),
            ("msg-2", "factory-b"),
        ]
    finally:
        store.close()


def test_outbox_append_and_mark_sent(tmp_path):
    store = SQLiteMessageStore(str(tmp_path))
    try:
        store.outbox_append(_envelope("msg-3", world_id="factory-b"))
        pending = store.outbox_read_pending(limit=10)
        assert [message.message_id for message in pending] == ["msg-3"]

        store.outbox_mark_sent("msg-3")
        assert store.outbox_read_pending(limit=10) == []
    finally:
        store.close()
