import os
import sys
import tempfile
import types

import pytest

from src.runtime.messaging import MessageEnvelope
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
        assert "factory-01" in wm.worlds
        assert wm.worlds["factory-01"]["runtime_status"] == "stopped"

        restart = await wm.handle_command(
            "world.start",
            {"world_id": "factory-01", "world_dir": f"{tmp}/factory-01"},
        )
        assert restart["status"] == "started"
        assert wm.worlds["factory-01"]["runtime_status"] == "running"

        removed = await wm.handle_command("world.remove", {"world_id": "factory-01"})
        assert removed["status"] == "removed"
        assert "factory-01" not in wm.worlds


@pytest.mark.anyio
async def test_unload_world_marks_pending_deliveries_dead_when_world_is_removed():
    with tempfile.TemporaryDirectory() as tmp:
        reg = WorldRegistry(base_dir=tmp)
        reg.create_world("factory-01")

        wm = WorkerManager(worker_id="wk-1")
        wm.load_worlds(tmp)
        hub = wm.build_message_hub(worker_dir=os.path.join(tmp, "messagebox"), channel=None)
        hub.on_inbound(
            MessageEnvelope(
                message_id="msg-1",
                source_world="external-erp",
                target_world="factory-01",
                event_type="order.created",
                payload={"order_id": "O1001"},
            )
        )
        hub._store.inbox_create_deliveries("msg-1", ["factory-01"])
        hub._store.inbox_mark_expanded("msg-1")

        assert wm.unload_world("factory-01") is True

        row = hub._store._conn.execute(
            "SELECT status, last_error FROM inbox_deliveries WHERE message_id = ? AND target_world_id = ?",
            ("msg-1", "factory-01"),
        ).fetchone()
        assert row == ("dead", "world permanently removed")


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


@pytest.mark.anyio
async def test_worker_manager_world_start_registers_receiver_and_sender():
    with tempfile.TemporaryDirectory() as tmp:
        wm = WorkerManager(worker_id="wk-1")
        wm.load_worlds(tmp)
        hub = wm.build_message_hub(worker_dir=os.path.join(tmp, "messagebox"), channel=None)

        reg = WorldRegistry(base_dir=tmp)
        reg.create_world("factory-01")

        result = await wm.handle_command(
            "world.start",
            {"world_id": "factory-01", "world_dir": f"{tmp}/factory-01"},
        )

        assert result["status"] == "started"
        assert "factory-01" in hub.registered_worlds()
        assert wm.worlds["factory-01"]["message_receiver"] is not None
        assert wm.worlds["factory-01"]["message_sender"] is not None
        assert wm.worlds["factory-01"]["state_manager"]._task is not None

        stop_result = await wm.handle_command("world.stop", {"world_id": "factory-01"})
        assert stop_result["status"] == "stopped"
        assert "factory-01" in wm.worlds

        remove_result = await wm.handle_command("world.remove", {"world_id": "factory-01"})
        assert remove_result["status"] == "removed"
        assert "factory-01" not in wm.worlds


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
        assert result["status"] == "running"

        await wm.handle_command("world.stop", {"world_id": "world-a"})
        stopped = await wm.handle_command("world.getStatus", {"world_id": "world-a"})
        assert stopped["status"] == "stopped"

        await wm.handle_command("world.remove", {"world_id": "world-a"})


def test_build_message_hub_rejects_conflicting_channel_binding():
    with tempfile.TemporaryDirectory() as tmp:
        reg = WorldRegistry(base_dir=tmp)
        reg.create_world("factory-01")

        wm = WorkerManager(worker_id="wk-1")
        wm.load_worlds(tmp)

        class _ChannelA:
            async def start(self, callback):
                return None

            async def stop(self):
                return None

            async def send(self, envelope):
                return None

            def is_ready(self):
                return True

        class _ChannelB(_ChannelA):
            pass

        wm.build_message_hub(worker_dir=os.path.join(tmp, "messagebox"), channel=_ChannelA())
        with pytest.raises(RuntimeError, match="different channel binding"):
            wm.build_message_hub(worker_dir=os.path.join(tmp, "messagebox"), channel=_ChannelB())


@pytest.mark.anyio
async def test_worker_manager_handle_command_message_hub_publish():
    """Verify messageHub.publish works when bundle has a message_hub."""
    with tempfile.TemporaryDirectory() as tmp:
        reg = WorldRegistry(base_dir=tmp)
        reg.create_world("factory-01")

        wm = WorkerManager(worker_id="wk-1")
        wm.load_worlds(tmp)

        # Create a minimal message_hub mock
        seen: list[MessageEnvelope] = []

        class _MockHub:
            def on_inbound(self, envelope: MessageEnvelope):
                seen.append(envelope)

            def unregister_world(self, world_id: str, *, permanent: bool = False):
                return None

        wm._message_hub = _MockHub()

        result = await wm.handle_command("messageHub.publish", {
            "message_id": "msg-1",
            "source_world": "external-erp",
            "target_world": "factory-01",
            "event_type": "test.event",
            "payload": {},
        })
        assert result["acked"] is True
        assert seen[0].message_id == "msg-1"
        assert seen[0].source_world == "external-erp"
        assert seen[0].target_world == "factory-01"
        assert seen[0].event_type == "test.event"

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
            def on_inbound(self, envelope: MessageEnvelope):
                seen_events.append((
                    envelope.message_id,
                    envelope.event_type,
                    envelope.source_world,
                    envelope.target_world,
                ))

            def unregister_world(self, world_id: str, *, permanent: bool = False):
                return None

        wm._message_hub = _MockHub()

        result = await wm.handle_command("messageHub.publishBatch", {
            "records": [
                {
                    "message_id": "r1",
                    "source_world": "external-erp",
                    "target_world": "factory-01",
                    "event_type": "e1",
                    "payload": {},
                },
                {
                    "message_id": "r2",
                    "source_world": "external-erp",
                    "target_world": "*",
                    "event_type": "e2",
                    "payload": {},
                },
            ],
        })
        assert result["acked_ids"] == ["r1", "r2"]
        assert seen_events == [
            ("r1", "e1", "external-erp", "factory-01"),
            ("r2", "e2", "external-erp", "*"),
        ]

        wm.unload_world("factory-01")
