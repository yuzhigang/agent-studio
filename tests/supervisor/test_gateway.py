import pytest
from src.supervisor.gateway import SupervisorGateway


@pytest.fixture
def gateway():
    return SupervisorGateway(base_dir="worlds")


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
