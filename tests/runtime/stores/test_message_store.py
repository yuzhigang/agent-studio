import pytest
from src.runtime.stores.sqlite_store import SQLiteStore


@pytest.fixture
def store(tmp_path):
    project_dir = str(tmp_path / "proj-01")
    s = SQLiteStore(project_dir)
    yield s
    s.close()


def test_inbox_enqueue_and_read_pending(store):
    msg_id = store.inbox_enqueue(
        "proj-01", "order.created", {"orderId": "123"}, "ext-1", "project", None
    )
    assert msg_id == 1

    pending = store.inbox_read_pending("proj-01", limit=10)
    assert len(pending) == 1
    assert pending[0]["id"] == msg_id
    assert pending[0]["event_type"] == "order.created"
    assert pending[0]["payload"] == {"orderId": "123"}
    assert pending[0]["source"] == "ext-1"
    assert pending[0]["scope"] == "project"
    assert pending[0]["target"] is None
    assert "received_at" in pending[0]


def test_inbox_mark_processed(store):
    msg_id = store.inbox_enqueue(
        "proj-01", "order.created", {"orderId": "123"}, "ext-1", "project", None
    )
    store.inbox_mark_processed("proj-01", msg_id)
    pending = store.inbox_read_pending("proj-01", limit=10)
    assert len(pending) == 0


def test_inbox_read_pending_ordering_and_limit(store):
    store.inbox_enqueue("proj-01", "a", {}, "s", "project", None)
    store.inbox_enqueue("proj-01", "b", {}, "s", "project", None)
    store.inbox_enqueue("proj-01", "c", {}, "s", "project", None)

    pending = store.inbox_read_pending("proj-01", limit=2)
    assert len(pending) == 2
    assert pending[0]["event_type"] == "a"
    assert pending[1]["event_type"] == "b"


def test_inbox_is_project_scoped(store):
    store.inbox_enqueue("proj-01", "a", {}, "s", "project", None)
    store.inbox_enqueue("proj-02", "b", {}, "s", "project", None)

    assert len(store.inbox_read_pending("proj-01", limit=10)) == 1
    assert len(store.inbox_read_pending("proj-02", limit=10)) == 1


def test_outbox_enqueue_and_read_pending(store):
    msg_id = store.outbox_enqueue(
        "proj-01", "order.shipped", {"orderId": "456"}, "inst-1", "project", "tgt-1"
    )
    assert msg_id == 1

    pending = store.outbox_read_pending("proj-01", limit=10)
    assert len(pending) == 1
    assert pending[0]["id"] == msg_id
    assert pending[0]["event_type"] == "order.shipped"
    assert pending[0]["payload"] == {"orderId": "456"}
    assert pending[0]["source"] == "inst-1"
    assert pending[0]["scope"] == "project"
    assert pending[0]["target"] == "tgt-1"
    assert pending[0]["error_count"] == 0


def test_outbox_mark_sent(store):
    msg_id = store.outbox_enqueue(
        "proj-01", "order.shipped", {}, "inst-1", "project", None
    )
    store.outbox_mark_sent("proj-01", msg_id)
    pending = store.outbox_read_pending("proj-01", limit=10)
    assert len(pending) == 0


def test_outbox_update_error(store):
    msg_id = store.outbox_enqueue(
        "proj-01", "order.shipped", {}, "inst-1", "project", None
    )
    store.outbox_update_error("proj-01", msg_id, error_count=3, retry_after="2099-01-01T00:00:00+00:00", last_error="timeout")
    pending = store.outbox_read_pending("proj-01", limit=10)
    # retry_after is in the future, should not be returned
    assert len(pending) == 0

    # Update to allow retry now-ish (use a past time)
    from datetime import datetime, timezone
    past = datetime.now(timezone.utc).isoformat()
    store.outbox_update_error("proj-01", msg_id, error_count=3, retry_after=past, last_error="timeout")
    pending = store.outbox_read_pending("proj-01", limit=10)
    assert len(pending) == 1
    assert pending[0]["error_count"] == 3


def test_outbox_max_retries_excluded(store):
    msg_id = store.outbox_enqueue(
        "proj-01", "order.shipped", {}, "inst-1", "project", None
    )
    store.outbox_update_error("proj-01", msg_id, error_count=10, retry_after=None, last_error="permanent failure")
    pending = store.outbox_read_pending("proj-01", limit=10)
    assert len(pending) == 0


def test_outbox_is_project_scoped(store):
    store.outbox_enqueue("proj-01", "a", {}, "s", "project", None)
    store.outbox_enqueue("proj-02", "b", {}, "s", "project", None)

    assert len(store.outbox_read_pending("proj-01", limit=10)) == 1
    assert len(store.outbox_read_pending("proj-02", limit=10)) == 1
