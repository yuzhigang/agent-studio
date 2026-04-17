import os
import tempfile

from src.runtime.message_hub import MessageHub
from src.runtime.project_registry import ProjectRegistry
from src.runtime.stores.sqlite_message_store import SQLiteMessageStore
from src.worker.cli.run_inline import _load_projects


def test_load_projects_inline():
    with tempfile.TemporaryDirectory() as tmp:
        reg1 = ProjectRegistry(base_dir=tmp)
        reg1.create_project("factory-01")
        reg2 = ProjectRegistry(base_dir=tmp)
        reg2.create_project("factory-02")
        dirs = [os.path.join(tmp, "factory-01"), os.path.join(tmp, "factory-02")]

        msg_store = SQLiteMessageStore(os.path.join(tmp, "messagebox"))
        message_hub = MessageHub(msg_store, None)
        registries = _load_projects(dirs, message_hub)

        assert registries[0].get_loaded_project("factory-01") is not None
        assert registries[1].get_loaded_project("factory-02") is not None

        bundle1 = registries[0].get_loaded_project("factory-01")
        bundle2 = registries[1].get_loaded_project("factory-02")
        assert bundle1["message_hub"] is message_hub
        assert bundle2["message_hub"] is message_hub
        assert bundle1["instance_manager"]._message_hub is message_hub
        assert bundle2["instance_manager"]._message_hub is message_hub

        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(message_hub.stop(), loop)
            else:
                loop.run_until_complete(message_hub.stop())
        except Exception:
            pass

        for r in registries:
            for pid in list(r._loaded.keys()):
                r.unload_project(pid)

        msg_store.close()
