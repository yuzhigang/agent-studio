import os
import signal
import sys

from src.runtime.message_hub import MessageHub
from src.runtime.project_registry import ProjectRegistry
from src.runtime.stores.sqlite_message_store import SQLiteMessageStore


def run_inline(project_dirs):
    worker_dir = os.path.join(os.path.expanduser("~"), ".agent-studio", "workers", "inline")
    msg_store = SQLiteMessageStore(worker_dir)
    message_hub = MessageHub(msg_store, None)
    registries = _load_projects(project_dirs, message_hub)

    def _shutdown(signum, frame):
        print("Shutting down inline runtime...")
        if message_hub is not None:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.run_coroutine_threadsafe(message_hub.stop(), loop)
                else:
                    loop.run_until_complete(message_hub.stop())
            except Exception:
                pass
        for registry in registries:
            for project_id in list(registry._loaded.keys()):
                registry.unload_project(project_id)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    import threading
    threading.Event().wait()
    return 0


def _load_projects(project_dirs, message_hub):
    registries = []
    for project_dir in project_dirs:
        base_dir = os.path.dirname(os.path.abspath(project_dir))
        project_id = os.path.basename(os.path.abspath(project_dir))
        registry = ProjectRegistry(base_dir=base_dir)
        bundle = registry.load_project(project_id)

        bus = bundle["event_bus_registry"].get_or_create(project_id)
        message_hub.register_project(project_id, bus, bundle.get("model_events", {}))
        bundle["instance_manager"]._message_hub = message_hub
        bundle["message_hub"] = message_hub

        # Start shared scenes
        store = bundle["store"]
        sm = bundle["scene_manager"]
        scenes = store.list_scenes(project_id)
        for scene_data in scenes:
            if scene_data.get("mode") == "shared":
                scene_id = scene_data["scene_id"]
                refs = scene_data.get("refs", [])
                local_instances = scene_data.get("local_instances", {})
                sm.start(project_id, scene_id, mode="shared", references=refs, local_instances=local_instances)

        registries.append(registry)

    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(message_hub.start(), loop)
        else:
            loop.run_until_complete(message_hub.start())
    except Exception:
        pass

    return registries
