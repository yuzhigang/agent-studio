import pytest
from src.runtime.stores.sqlite_message_store import SQLiteMessageStore


@pytest.fixture
def store(tmp_path):
    s = SQLiteMessageStore(str(tmp_path))
    yield s
    s.close()


def test_inbox_enqueue_and_read_pending(store):
    mid = store.inbox_enqueue(
        event_type="evt.a",
        payload={"x": 1},
        source="src-1",
        scope="project",
        target="tgt-1",
    )
    assert isinstance(mid, int)

    pending = store.inbox_read_pending(limit=10)
    assert len(pending) == 1
    assert pending[0]["id"] == mid
    assert pending[0]["event_type"] == "evt.a"
    assert pending[0]["payload"] == {"x": 1}
    assert pending[0]["source"] == "src-1"
    assert pending[0]["scope"] == "project"
    assert pending[0]["target"] == "tgt-1"
    assert "received_at" in pending[0]


def test_inbox_mark_processed(store):
    mid = store.inbox_enqueue(
        event_type="evt.b",
        payload={},
        source="src-1",
        scope="project",
        target=None,
    )
    store.inbox_mark_processed(mid)
    pending = store.inbox_read_pending(limit=10)
    assert len(pending) == 0


def test_outbox_enqueue_and_read_pending(store):
    mid = store.outbox_enqueue(
        event_type="evt.c",
        payload={"y": 2},
        source="src-2",
        scope="scene:s1",
        target="tgt-2",
    )
    assert isinstance(mid, int)

    pending = store.outbox_read_pending(limit=10)
    assert len(pending) == 1
    assert pending[0]["id"] == mid
    assert pending[0]["event_type"] == "evt.c"
    assert pending[0]["payload"] == {"y": 2}
    assert pending[0]["source"] == "src-2"
    assert pending[0]["scope"] == "scene:s1"
    assert pending[0]["target"] == "tgt-2"
    assert "created_at" in pending[0]


def test_outbox_mark_sent(store):
    mid = store.outbox_enqueue(
        event_type="evt.d",
        payload={},
        source="src-2",
        scope="project",
        target=None,
    )
    store.outbox_mark_sent(mid)
    pending = store.outbox_read_pending(limit=10)
    assert len(pending) == 0


def test_outbox_update_error_with_retry_after(store):
    from datetime import datetime, timedelta, timezone

    mid = store.outbox_enqueue(
        event_type="evt.e",
        payload={},
        source="src-3",
        scope="project",
        target=None,
    )

    future = (datetime.now(timezone.utc) + timedelta(seconds=300)).isoformat()
    store.outbox_update_error(mid, error_count=1, retry_after=future, last_error="timeout")
    pending = store.outbox_read_pending(limit=10)
    assert len(pending) == 0

    past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    store.outbox_update_error(mid, error_count=2, retry_after=past, last_error="timeout")
    pending = store.outbox_read_pending(limit=10)
    assert len(pending) == 1
    assert pending[0]["id"] == mid
    assert pending[0]["error_count"] == 2
    assert pending[0]["last_error"] == "timeout"
