import asyncio

import pytest

from src.supervisor.gateway import WorkerController, WorkerState


@pytest.fixture
def gateway():
    return WorkerController(base_dir="worlds")


# --- Backward compatibility tests ---

def test_register_runtime(gateway):
    class FakeWs:
        def __init__(self):
            self.closed = False
            self.sent = []
        async def send(self, msg):
            self.sent.append(msg)
        async def close(self):
            self.closed = True

    ws = FakeWs()
    gateway.register_runtime_sync("world-a", ws, "sess-1")
    rt = gateway.get_runtime("world-a")
    assert rt[0] == ws
    assert rt[1] == "sess-1"


def test_replace_runtime_session(gateway):
    class FakeWs:
        def __init__(self):
            self.closed = False
            self.sent = []
        async def send(self, msg):
            self.sent.append(msg)
        async def close(self):
            self.closed = True

    ws1 = FakeWs()
    ws2 = FakeWs()
    gateway.register_runtime_sync("world-a", ws1, "sess-1")
    gateway.register_runtime_sync("world-a", ws2, "sess-2")
    assert ws1.closed is True
    rt = gateway.get_runtime("world-a")
    assert rt[0] == ws2
    assert rt[1] == "sess-2"


# --- New Worker-level API tests ---

@pytest.mark.anyio
async def test_register_worker(gateway):
    class FakeWs:
        def __init__(self):
            self.closed = False
            self.sent = []
        async def send_str(self, msg):
            self.sent.append(msg)
        async def close(self):
            self.closed = True

    ws = FakeWs()
    await gateway.register_worker("wk-1", ws, "sess-1", ["world-a", "world-b"])

    worker = gateway.get_worker("wk-1")
    assert worker is not None
    assert worker.session_id == "sess-1"
    assert worker.world_ids == ["world-a", "world-b"]

    assert gateway.get_worker_by_world("world-a") == worker
    assert gateway.get_worker_by_world("world-b") == worker

    # broadcast was sent
    assert len(ws.sent) == 0  # ws is the worker ws, not a client


@pytest.mark.anyio
async def test_unregister_worker(gateway):
    class FakeWs:
        def __init__(self):
            self.closed = False
        async def close(self):
            self.closed = True

    ws = FakeWs()
    await gateway.register_worker("wk-1", ws, "sess-1", ["world-a"])
    await gateway.unregister_worker("wk-1")

    assert gateway.get_worker("wk-1") is None
    assert gateway.get_worker_by_world("world-a") is None


@pytest.mark.anyio
async def test_send_to_worker(gateway):
    class FakeWs:
        def __init__(self):
            self.sent = []
        async def send_str(self, msg):
            self.sent.append(msg)

    ws = FakeWs()
    await gateway.register_worker("wk-1", ws, "sess-1", ["world-a"])

    ok = await gateway.send_to_worker("wk-1", {"test": "msg"})
    assert ok is True
    assert len(ws.sent) == 1


@pytest.mark.anyio
async def test_send_to_worker_by_world(gateway):
    class FakeWs:
        def __init__(self):
            self.sent = []
        async def send_str(self, msg):
            self.sent.append(msg)

    ws = FakeWs()
    await gateway.register_worker("wk-1", ws, "sess-1", ["world-a"])

    ok = await gateway.send_to_worker_by_world("world-a", {"test": "msg"})
    assert ok is True
    assert len(ws.sent) == 1


@pytest.mark.anyio
async def test_update_heartbeat(gateway):
    class FakeWs:
        pass

    ws = FakeWs()
    await gateway.register_worker("wk-1", ws, "sess-1", ["world-a"])

    old_hb = gateway.get_worker("wk-1").last_heartbeat
    await asyncio.sleep(0.01)
    await gateway.update_heartbeat("wk-1")
    new_hb = gateway.get_worker("wk-1").last_heartbeat
    assert new_hb > old_hb


@pytest.mark.anyio
async def test_worker_replacement_closes_old(gateway):
    class FakeWs:
        def __init__(self):
            self.closed = False
        async def close(self):
            self.closed = True

    ws1 = FakeWs()
    ws2 = FakeWs()
    await gateway.register_worker("wk-1", ws1, "sess-1", ["world-a"])
    await gateway.register_worker("wk-1", ws2, "sess-2", ["world-b"])

    assert ws1.closed is True
    assert gateway.get_worker_by_world("world-a") is None
    assert gateway.get_worker_by_world("world-b") is not None
