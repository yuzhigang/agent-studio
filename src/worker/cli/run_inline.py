import os
import signal
import sys

from src.runtime.message_hub import MessageHub
from src.runtime.world_registry import WorldRegistry
from src.runtime.stores.sqlite_message_store import SQLiteMessageStore


def run_inline(world_dirs):
    worker_dir = os.path.join(os.path.expanduser("~"), ".agent-studio", "workers", "inline")
    msg_store = SQLiteMessageStore(worker_dir)
    message_hub = MessageHub(msg_store, None)
    registries = _load_worlds(world_dirs, message_hub)

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
            for world_id in list(registry._loaded.keys()):
                registry.unload_world(world_id)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    import threading
    threading.Event().wait()
    return 0


def _load_worlds(world_dirs, message_hub):
    registries = []
    for world_dir in world_dirs:
        base_dir = os.path.dirname(os.path.abspath(world_dir))
        world_id = os.path.basename(os.path.abspath(world_dir))
        registry = WorldRegistry(base_dir=base_dir)
        bundle = registry.load_world(world_id)

        bus = bundle["event_bus_registry"].get_or_create(world_id)
        message_hub.register_world(world_id, bus, bundle.get("model_events", {}))
        bundle["instance_manager"]._message_hub = message_hub
        bundle["message_hub"] = message_hub

        # Start shared scenes
        store = bundle["store"]
        sm = bundle["scene_manager"]
        scenes = store.list_scenes(world_id)
        for scene_data in scenes:
            if scene_data.get("mode") == "shared":
                scene_id = scene_data["scene_id"]
                refs = scene_data.get("refs", [])
                local_instances = scene_data.get("local_instances", {})
                sm.start(world_id, scene_id, mode="shared", references=refs, local_instances=local_instances)

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
