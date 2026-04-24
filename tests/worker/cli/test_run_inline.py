import os
import tempfile

import pytest

from src.runtime.message_hub import MessageHub
from src.runtime.world_registry import WorldRegistry
from src.runtime.stores.sqlite_message_store import SQLiteMessageStore
from src.worker.manager import WorkerManager


def test_run_inline_world_loading():
    with tempfile.TemporaryDirectory() as tmp:
        reg = WorldRegistry(base_dir=tmp)
        reg.create_world("factory-01")
        reg.create_world("factory-02")

        wm = WorkerManager()
        wm.load_worlds(tmp)

        assert "factory-01" in wm.worlds
        assert "factory-02" in wm.worlds

        # Simulate MessageHub setup as run_inline does
        msg_store = SQLiteMessageStore(os.path.join(tmp, "messagebox"))
        message_hub = MessageHub(msg_store, None)

        for world_id, bundle in wm.worlds.items():
            bus = bundle["event_bus_registry"].get_or_create(world_id)
            message_hub.register_world(world_id, bus, bundle.get("model_events", {}))
            bundle["message_hub"] = message_hub

        bundle1 = wm.worlds["factory-01"]
        bundle2 = wm.worlds["factory-02"]
        assert bundle1["message_hub"] is message_hub
        assert bundle2["message_hub"] is message_hub

        # cleanup
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(message_hub.stop(), loop)
            else:
                loop.run_until_complete(message_hub.stop())
        except Exception:
            pass

        for wid in list(wm.worlds.keys()):
            wm.unload_world(wid)

        msg_store.close()
