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


@pytest.mark.anyio
async def test_worker_manager_handle_command_world_stop():
    with tempfile.TemporaryDirectory() as tmp:
        reg = WorldRegistry(base_dir=tmp)
        reg.create_world("factory-01")

        wm = WorkerManager(worker_id="wk-1")
        wm.load_worlds(tmp)

        result = await wm.handle_command("world.stop", {"world_id": "factory-01"})
        assert result["status"] == "stopped"
        assert "factory-01" not in wm.worlds


@pytest.mark.anyio
async def test_worker_manager_handle_command_world_checkpoint():
    with tempfile.TemporaryDirectory() as tmp:
        reg = WorldRegistry(base_dir=tmp)
        reg.create_world("world-a")

        wm = WorkerManager(worker_id="wk-1")
        wm.load_worlds(tmp)

        result = await wm.handle_command("world.checkpoint", {"world_id": "world-a"})
        assert result["status"] == "checkpointed"

        # cleanup
        wm.unload_world("world-a")


def test_worker_manager_handle_command_unknown_world():
    wm = WorkerManager(worker_id="wk-1")
    with pytest.raises(Exception) as exc_info:
        # Use asyncio.run since there's no running loop in a sync test
        import asyncio
        asyncio.run(wm.handle_command("world.stop", {"world_id": "nonexistent"}))
    assert "-32004" in str(exc_info.value)


@pytest.mark.anyio
async def test_worker_manager_handle_command_unknown_method():
    with tempfile.TemporaryDirectory() as tmp:
        reg = WorldRegistry(base_dir=tmp)
        reg.create_world("world-a")

        wm = WorkerManager(worker_id="wk-1")
        wm.load_worlds(tmp)

        with pytest.raises(Exception) as exc_info:
            await wm.handle_command("world.unknown", {"world_id": "world-a"})
        assert "-32601" in str(exc_info.value)

        wm.unload_world("world-a")


@pytest.mark.anyio
async def test_worker_manager_handle_command_world_get_status():
    with tempfile.TemporaryDirectory() as tmp:
        reg = WorldRegistry(base_dir=tmp)
        reg.create_world("world-a")

        wm = WorkerManager(worker_id="wk-1")
        wm.load_worlds(tmp)

        result = await wm.handle_command("world.getStatus", {"world_id": "world-a"})
        assert result["loaded"] is True
        assert result["world_id"] == "world-a"

        wm.unload_world("world-a")


@pytest.mark.anyio
async def test_worker_manager_handle_command_message_hub_publish():
    """Verify messageHub.publish works when bundle has a message_hub."""
    with tempfile.TemporaryDirectory() as tmp:
        reg = WorldRegistry(base_dir=tmp)
        reg.create_world("factory-01")

        wm = WorkerManager(worker_id="wk-1")
        wm.load_worlds(tmp)

        # Create a minimal message_hub mock
        class _MockHub:
            def on_channel_message(self, event_type, payload, source, scope, target):
                pass

        wm.worlds["factory-01"]["message_hub"] = _MockHub()

        result = await wm.handle_command("messageHub.publish", {
            "world_id": "factory-01",
            "event_type": "test.event",
            "payload": {},
        })
        assert result["acked"] is True

        wm.unload_world("factory-01")


@pytest.mark.anyio
async def test_worker_manager_handle_command_message_hub_publish_batch():
    """Verify messageHub.publishBatch works when bundle has a message_hub."""
    with tempfile.TemporaryDirectory() as tmp:
        reg = WorldRegistry(base_dir=tmp)
        reg.create_world("factory-01")

        wm = WorkerManager(worker_id="wk-1")
        wm.load_worlds(tmp)

        seen_events = []

        class _MockHub:
            def on_channel_message(self, event_type, payload, source, scope, target):
                seen_events.append(event_type)

        wm.worlds["factory-01"]["message_hub"] = _MockHub()

        result = await wm.handle_command("messageHub.publishBatch", {
            "world_id": "factory-01",
            "records": [
                {"id": "r1", "event_type": "e1", "payload": {}},
                {"id": "r2", "event_type": "e2", "payload": {}},
            ],
        })
        assert result["acked_ids"] == ["r1", "r2"]
        assert seen_events == ["e1", "e2"]

        wm.unload_world("factory-01")
