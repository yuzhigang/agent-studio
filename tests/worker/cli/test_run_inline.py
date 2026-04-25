import os
import sys
import tempfile
import types

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


def test_run_inline_registers_message_receivers_for_all_worlds():
    with tempfile.TemporaryDirectory() as tmp:
        reg = WorldRegistry(base_dir=tmp)
        reg.create_world("factory-01")
        reg.create_world("factory-02")

        wm = WorkerManager()
        wm.load_worlds(tmp)

        message_hub = wm.build_message_hub(
            worker_dir=os.path.join(tmp, "messagebox"),
            channel=None,
        )

        bundle1 = wm.worlds["factory-01"]
        bundle2 = wm.worlds["factory-02"]
        assert sorted(message_hub.registered_worlds()) == ["factory-01", "factory-02"]
        assert bundle1["message_hub"] is message_hub
        assert bundle1["message_receiver"] is not None
        assert bundle2["message_hub"] is message_hub
        assert bundle2["message_sender"] is not None

        # cleanup
        for wid in list(wm.worlds.keys()):
            wm.unload_world(wid)
