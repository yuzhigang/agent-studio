import os
import sys
import tempfile
import types

import pytest

from src.runtime.world_registry import WorldRegistry

if "websockets" not in sys.modules:
    websockets_module = types.ModuleType("websockets")
    protocol_module = types.ModuleType("websockets.protocol")

    class _State:
        OPEN = "OPEN"

    protocol_module.State = _State
    websockets_module.protocol = protocol_module
    sys.modules["websockets"] = websockets_module
    sys.modules["websockets.protocol"] = protocol_module

from src.worker.cli.run_command import _start_shared_scenes, _graceful_shutdown, _send_heartbeats


def test_start_shared_scenes_restores_shared():
    with tempfile.TemporaryDirectory() as tmp:
        reg = WorldRegistry(base_dir=tmp)
        reg.create_world("world-a")
        bundle = reg.load_world("world-a")
        sm = bundle["scene_manager"]
        store = bundle["store"]
        # create a shared scene via scene manager and persist it
        sm.start("world-a", "scene-1", mode="shared")
        sm.checkpoint_scene("world-a", "scene-1")
        reg.unload_world("world-a")

        # reload and auto-start shared scenes
        bundle2 = reg.load_world("world-a")
        _start_shared_scenes(bundle2)
        assert bundle2["scene_manager"].get("world-a", "scene-1") is not None
        reg.unload_world("world-a")


def test_graceful_shutdown_unloads_and_releases_lock():
    with tempfile.TemporaryDirectory() as tmp:
        reg = WorldRegistry(base_dir=tmp)
        reg.create_world("world-a")
        bundle = reg.load_world("world-a")
        _graceful_shutdown(bundle)
        assert reg.get_loaded_world("world-a") is None
        # lock should be released, so reload works
        bundle2 = reg.load_world("world-a")
        assert bundle2 is not None
        reg.unload_world("world-a")


@pytest.mark.anyio
async def test_send_heartbeats_reports_runtime_status(monkeypatch):
    class FakeWS:
        def __init__(self):
            self.closed = False

    class FakeConn:
        def __init__(self, ws):
            self.sent = []
            self._ws = ws

        def build_notification(self, method, params):
            return {"method": method, "params": params}

        async def send(self, payload):
            self.sent.append(payload)
            self._ws.closed = True

    class FakeSceneManager:
        def list_by_world(self, world_id):
            return [{"scene_id": "scene-1", "mode": "isolated"}]

    class FakeInstanceManager:
        def list_by_world(self, world_id):
            return [object(), object()]

    class FakeWorkerManager:
        worker_id = "wk-1"
        session_id = "sess-1"
        worlds = {
            "world-a": {
                "runtime_status": "stopped",
                "scene_manager": FakeSceneManager(),
                "instance_manager": FakeInstanceManager(),
            }
        }

    async def _fast_sleep(_seconds):
        return None

    monkeypatch.setattr("src.worker.cli.run_command.asyncio.sleep", _fast_sleep)

    ws = FakeWS()
    conn = FakeConn(ws)
    await _send_heartbeats(ws, conn, FakeWorkerManager())

    assert len(conn.sent) == 1
    payload = conn.sent[0]
    assert payload["method"] == "notify.worker.heartbeat"
    assert payload["params"]["worlds"]["world-a"]["status"] == "stopped"
    assert payload["params"]["worlds"]["world-a"]["scene_count"] == 1
    assert payload["params"]["worlds"]["world-a"]["instance_count"] == 2
