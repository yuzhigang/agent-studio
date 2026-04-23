import os
import tempfile

import pytest

from src.runtime.world_registry import WorldRegistry
from src.worker.manager import WorkerManager


def test_worker_manager_init():
    wm = WorkerManager(worker_id="wk-1")
    assert wm.worker_id == "wk-1"
    assert wm.session_id is not None
    assert wm.worlds == {}


def test_worker_manager_load_worlds():
    with tempfile.TemporaryDirectory() as tmp:
        reg = WorldRegistry(base_dir=tmp)
        reg.create_world("factory-01")
        reg.create_world("factory-02")

        wm = WorkerManager(worker_id="wk-1")
        world_ids = wm.load_worlds(tmp)

        assert "factory-01" in wm.worlds
        assert "factory-02" in wm.worlds
        assert set(world_ids) == {"factory-01", "factory-02"}

        # Cleanup
        for wid in list(wm.worlds.keys()):
            wm.unload_world(wid)


def test_worker_manager_handle_command_world_stop():
    with tempfile.TemporaryDirectory() as tmp:
        reg = WorldRegistry(base_dir=tmp)
        reg.create_world("factory-01")

        wm = WorkerManager(worker_id="wk-1")
        wm.load_worlds(tmp)

        result = wm.handle_command("world.stop", {"world_id": "factory-01"})
        assert result["status"] == "stopped"
        assert "factory-01" not in wm.worlds


def test_worker_manager_handle_command_world_checkpoint():
    with tempfile.TemporaryDirectory() as tmp:
        reg = WorldRegistry(base_dir=tmp)
        reg.create_world("world-a")

        wm = WorkerManager(worker_id="wk-1")
        wm.load_worlds(tmp)

        result = wm.handle_command("world.checkpoint", {"world_id": "world-a"})
        assert result["status"] == "checkpointed"

        # cleanup
        wm.unload_world("world-a")


def test_worker_manager_handle_command_unknown_world():
    wm = WorkerManager(worker_id="wk-1")
    with pytest.raises(Exception) as exc_info:
        wm.handle_command("world.stop", {"world_id": "nonexistent"})
    assert "-32004" in str(exc_info.value)


def test_worker_manager_handle_command_unknown_method():
    with tempfile.TemporaryDirectory() as tmp:
        reg = WorldRegistry(base_dir=tmp)
        reg.create_world("world-a")

        wm = WorkerManager(worker_id="wk-1")
        wm.load_worlds(tmp)

        with pytest.raises(Exception) as exc_info:
            wm.handle_command("world.unknown", {"world_id": "world-a"})
        assert "-32601" in str(exc_info.value)

        wm.unload_world("world-a")
