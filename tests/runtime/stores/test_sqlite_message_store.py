import pytest

from src.runtime.messaging.envelope import MessageEnvelope
from src.runtime.messaging.sqlite_store import SQLiteMessageStore


@pytest.fixture
def store(tmp_path):
    s = SQLiteMessageStore(str(tmp_path))
    yield s
    s.close()


def test_inbox_append_and_read_pending(store):
    envelope = MessageEnvelope(
        message_id="msg-1",
        source_world="factory-upstream",
        target_world="factory-a",
        event_type="evt.a",
        payload={"x": 1},
        source="src-1",
        target="tgt-1",
    )
    store.inbox_append(envelope)

    pending = store.inbox_read_pending(limit=10)
    assert len(pending) == 1
    assert pending[0] == envelope
    assert pending[0].source_world == "factory-upstream"
    assert pending[0].target_world == "factory-a"


def test_inbox_deliveries_reconcile_to_completed(store):
    envelope = MessageEnvelope(
        message_id="msg-2",
        source_world="factory-upstream",
        target_world="factory-a",
        event_type="evt.b",
        payload={},
        source="src-1",
    )
    store.inbox_append(envelope)
    store.inbox_create_deliveries("msg-2", ["factory-a"])
    store.inbox_mark_expanded("msg-2")
    store.inbox_mark_delivery_delivered("msg-2", "factory-a")
    store.inbox_reconcile_statuses()

    row = store._conn.execute(
        "SELECT status FROM inbox WHERE message_id = ?",
        ("msg-2",),
    ).fetchone()
    assert row == ("completed",)


def test_outbox_append_and_read_pending(store):
    envelope = MessageEnvelope(
        message_id="msg-3",
        source_world="factory-b",
        target_world=None,
        event_type="evt.c",
        payload={"y": 2},
        source="src-2",
        scope="scene:s1",
        target="tgt-2",
    )
    store.outbox_append(envelope)

    pending = store.outbox_read_pending(limit=10)
    assert len(pending) == 1
    assert pending[0] == envelope
    assert pending[0].source_world == "factory-b"
    assert pending[0].target_world is None


def test_outbox_mark_sent(store):
    store.outbox_append(
        MessageEnvelope(
            message_id="msg-4",
            source_world="factory-b",
            target_world=None,
            event_type="evt.d",
            payload={},
            source="src-2",
        )
    )
    store.outbox_mark_sent("msg-4")
    pending = store.outbox_read_pending(limit=10)
    assert len(pending) == 0


def test_outbox_mark_retry_with_retry_after(store):
    from datetime import datetime, timedelta, timezone

    store.outbox_append(
        MessageEnvelope(
            message_id="msg-5",
            source_world="factory-b",
            target_world=None,
            event_type="evt.e",
            payload={},
            source="src-3",
        )
    )

    future = (datetime.now(timezone.utc) + timedelta(seconds=300)).isoformat()
    store.outbox_mark_retry(
        "msg-5",
        error_count=1,
        retry_after=future,
        last_error="timeout",
    )
    pending = store.outbox_read_pending(limit=10)
    assert len(pending) == 0

    past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    store.outbox_mark_retry(
        "msg-5",
        error_count=2,
        retry_after=past,
        last_error="timeout",
    )
    pending = store.outbox_read_pending(limit=10)
    assert len(pending) == 1
    assert pending[0].message_id == "msg-5"
    assert pending[0].source_world == "factory-b"
    assert pending[0].target_world is None
    row = store._conn.execute(
        "SELECT status, error_count, last_error FROM outbox WHERE message_id = ?",
        ("msg-5",),
    ).fetchone()
    assert row == ("retry", 2, "timeout")
