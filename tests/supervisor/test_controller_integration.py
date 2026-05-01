import pytest

from src.supervisor.worker import WorkerController


@pytest.mark.anyio
async def test_worker_registration_roundtrip():
    controller = WorkerController()

    class FakeWs:
        def __init__(self):
            self.sent = []
            self.closed = False
        async def send_str(self, msg):
            self.sent.append(msg)
        async def close(self):
            self.closed = True

    ws = FakeWs()
    await controller.register_worker("wk-1", ws, "sess-1", ["world-a"])

    worker = controller.get_worker("wk-1")
    assert worker.worker_id == "wk-1"
    assert controller.get_worker_by_world("world-a").worker_id == "wk-1"

    await controller.unregister_worker("wk-1")
    assert controller.get_worker("wk-1") is None
    assert controller.get_worker_by_world("world-a") is None


@pytest.mark.anyio
async def test_worker_replacement_broadcasts_reset():
    controller = WorkerController()

    class FakeWs:
        def __init__(self):
            self.sent = []
            self.closed = False
        async def send_str(self, msg):
            self.sent.append(msg)
        async def close(self):
            self.closed = True

    client_ws = FakeWs()
    await controller.add_client(client_ws)

    worker_ws = FakeWs()
    await controller.register_worker("wk-1", worker_ws, "sess-1", ["world-a"])

    # Client should have received notify.worker.activated
    assert len(client_ws.sent) == 1
    msg = client_ws.sent[0]
    assert "notify.worker.activated" in msg
