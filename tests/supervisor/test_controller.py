import asyncio

import pytest

from src.supervisor.worker import WorkerController, WorkerState


@pytest.fixture
def controller():
    return WorkerController(base_dir="worlds")


@pytest.mark.anyio
async def test_register_worker(controller):
    class FakeWs:
        def __init__(self):
            self.closed = False
            self.sent = []
        async def send_str(self, msg):
            self.sent.append(msg)
        async def close(self):
            self.closed = True

    ws = FakeWs()
    await controller.register_worker("wk-1", ws, "sess-1", ["world-a", "world-b"])

    worker = controller.get_worker("wk-1")
    assert worker is not None
    assert worker.session_id == "sess-1"
    assert worker.world_ids == ["world-a", "world-b"]

    assert controller.get_worker_by_world("world-a") == worker
    assert controller.get_worker_by_world("world-b") == worker

    # broadcast was sent
    assert len(ws.sent) == 0  # ws is the worker ws, not a client


@pytest.mark.anyio
async def test_unregister_worker(controller):
    class FakeWs:
        def __init__(self):
            self.closed = False
        async def close(self):
            self.closed = True

    ws = FakeWs()
    await controller.register_worker("wk-1", ws, "sess-1", ["world-a"])
    await controller.unregister_worker("wk-1")

    assert controller.get_worker("wk-1") is None
    assert controller.get_worker_by_world("world-a") is None


@pytest.mark.anyio
async def test_send_to_worker(controller):
    class FakeWs:
        def __init__(self):
            self.sent = []
        async def send_str(self, msg):
            self.sent.append(msg)

    ws = FakeWs()
    await controller.register_worker("wk-1", ws, "sess-1", ["world-a"])

    ok = await controller.send_to_worker("wk-1", {"test": "msg"})
    assert ok is True
    assert len(ws.sent) == 1


@pytest.mark.anyio
async def test_send_to_worker_by_world(controller):
    class FakeWs:
        def __init__(self):
            self.sent = []
        async def send_str(self, msg):
            self.sent.append(msg)

    ws = FakeWs()
    await controller.register_worker("wk-1", ws, "sess-1", ["world-a"])

    ok = await controller.send_to_worker_by_world("world-a", {"test": "msg"})
    assert ok is True
    assert len(ws.sent) == 1


@pytest.mark.anyio
async def test_update_heartbeat(controller):
    class FakeWs:
        pass

    ws = FakeWs()
    await controller.register_worker("wk-1", ws, "sess-1", ["world-a"])

    old_hb = controller.get_worker("wk-1").last_heartbeat
    await asyncio.sleep(0.01)
    await controller.update_heartbeat("wk-1")
    new_hb = controller.get_worker("wk-1").last_heartbeat
    assert new_hb > old_hb


@pytest.mark.anyio
async def test_worker_replacement_closes_old(controller):
    class FakeWs:
        def __init__(self):
            self.closed = False
        async def close(self):
            self.closed = True

    ws1 = FakeWs()
    ws2 = FakeWs()
    await controller.register_worker("wk-1", ws1, "sess-1", ["world-a"])
    await controller.register_worker("wk-1", ws2, "sess-2", ["world-b"])

    assert ws1.closed is True
    assert controller.get_worker_by_world("world-a") is None
    assert controller.get_worker_by_world("world-b") is not None
