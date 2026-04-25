from src.runtime.messaging import MessageEnvelope
from src.runtime.messaging.sqlite_store import SQLiteMessageStore


def _envelope(
    message_id: str,
    *,
    source_world: str | None = "factory-a",
    target_world: str | None = "factory-b",
    target: str | None = None,
) -> MessageEnvelope:
    return MessageEnvelope(
        message_id=message_id,
        source_world=source_world,
        target_world=target_world,
        event_type="order.created",
        payload={"order_id": message_id},
        source="erp",
        target=target,
    )


def test_inbox_append_and_expand_delivery(tmp_path):
    store = SQLiteMessageStore(str(tmp_path))
    try:
        store.inbox_append(_envelope("msg-1"))
        pending = store.inbox_read_pending(limit=10)
        assert [message.message_id for message in pending] == ["msg-1"]
        assert pending[0].source_world == "factory-a"
        assert pending[0].target_world == "factory-b"

        store.inbox_create_deliveries("msg-1", ["factory-a"])
        deliveries = store.inbox_read_pending_deliveries(limit=10)
        assert [(delivery.message_id, delivery.target_world) for delivery in deliveries] == [
            ("msg-1", "factory-a")
        ]
    finally:
        store.close()


def test_broadcast_delivery_is_unique_per_world(tmp_path):
    store = SQLiteMessageStore(str(tmp_path))
    try:
        store.inbox_append(_envelope("msg-2", target_world="*"))
        store.inbox_create_deliveries("msg-2", ["factory-a", "factory-b"])
        store.inbox_create_deliveries("msg-2", ["factory-a", "factory-b"])

        deliveries = store.inbox_read_pending_deliveries(limit=10)
        assert sorted((delivery.message_id, delivery.target_world) for delivery in deliveries) == [
            ("msg-2", "factory-a"),
            ("msg-2", "factory-b"),
        ]
    finally:
        store.close()


def test_outbox_append_and_mark_sent(tmp_path):
    store = SQLiteMessageStore(str(tmp_path))
    try:
        store.outbox_append(_envelope("msg-3", source_world="factory-b", target_world=None))
        pending = store.outbox_read_pending(limit=10)
        assert [message.message_id for message in pending] == ["msg-3"]
        assert pending[0].source_world == "factory-b"
        assert pending[0].target_world is None

        store.outbox_mark_sent("msg-3")
        assert store.outbox_read_pending(limit=10) == []
    finally:
        store.close()


def test_sqlite_schema_uses_source_world_and_target_world_columns(tmp_path):
    store = SQLiteMessageStore(str(tmp_path))
    try:
        inbox_columns = {
            row[1] for row in store._conn.execute("PRAGMA table_info(inbox)").fetchall()
        }
        outbox_columns = {
            row[1] for row in store._conn.execute("PRAGMA table_info(outbox)").fetchall()
        }

        assert "source_world" in inbox_columns
        assert "target_world" in inbox_columns
        assert "world_id" not in inbox_columns
        assert "source_world" in outbox_columns
        assert "target_world" in outbox_columns
        assert "world_id" not in outbox_columns
    finally:
        store.close()


def test_outbox_round_trips_source_world_target_world_and_target(tmp_path):
    store = SQLiteMessageStore(str(tmp_path))
    try:
        store.outbox_append(
            _envelope(
                "msg-roundtrip",
                source_world="world-a",
                target_world="world-b",
                target="ladle-002",
            )
        )

        stored = store.outbox_read_pending(limit=10)[0]

        assert stored.source_world == "world-a"
        assert stored.target_world == "world-b"
        assert stored.target == "ladle-002"
    finally:
        store.close()


def test_inbox_reconcile_all_delivered_sets_completed(tmp_path):
    store = SQLiteMessageStore(str(tmp_path))
    try:
        store.inbox_append(_envelope("msg-all-ok"))
        store.inbox_create_deliveries("msg-all-ok", ["factory-a", "factory-b"])
        store.inbox_mark_expanded("msg-all-ok")
        store.inbox_mark_delivery_delivered("msg-all-ok", "factory-a")
        store.inbox_mark_delivery_delivered("msg-all-ok", "factory-b")

        store.inbox_reconcile_statuses()

        row = store._conn.execute(
            "SELECT status FROM inbox WHERE message_id = ?", ("msg-all-ok",)
        ).fetchone()
        assert row == ("completed",)
    finally:
        store.close()


def test_inbox_reconcile_mixed_terminal_sets_failed(tmp_path):
    store = SQLiteMessageStore(str(tmp_path))
    try:
        store.inbox_append(_envelope("msg-mixed"))
        store.inbox_create_deliveries("msg-mixed", ["factory-a", "factory-b"])
        store.inbox_mark_expanded("msg-mixed")
        store.inbox_mark_delivery_delivered("msg-mixed", "factory-a")
        store.inbox_mark_delivery_dead("msg-mixed", "factory-b", error_count=1, last_error="boom")

        store.inbox_reconcile_statuses()

        row = store._conn.execute(
            "SELECT status FROM inbox WHERE message_id = ?", ("msg-mixed",)
        ).fetchone()
        assert row == ("failed",)
    finally:
        store.close()


def test_inbox_reconcile_partial_pending_leaves_expanded(tmp_path):
    """When some deliveries are still pending/retry, inbox stays expanded.
    Documents current behaviour.
    """
    store = SQLiteMessageStore(str(tmp_path))
    try:
        store.inbox_append(_envelope("msg-partial"))
        store.inbox_create_deliveries("msg-partial", ["factory-a", "factory-b"])
        store.inbox_mark_expanded("msg-partial")
        store.inbox_mark_delivery_delivered("msg-partial", "factory-a")
        # factory-b stays pending

        store.inbox_reconcile_statuses()

        row = store._conn.execute(
            "SELECT status FROM inbox WHERE message_id = ?", ("msg-partial",)
        ).fetchone()
        assert row == ("expanded",)
    finally:
        store.close()
