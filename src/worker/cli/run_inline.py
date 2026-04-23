import os
import signal
import sys

from src.runtime.message_hub import MessageHub
from src.runtime.world_registry import WorldRegistry
from src.runtime.stores.sqlite_message_store import SQLiteMessageStore
from src.worker.manager import WorkerManager


def run_inline(world_dirs, supervisor_ws=None):
    if not world_dirs:
        return 0

    worker_manager = WorkerManager()

    # Load each specified world
    for world_dir in world_dirs:
        base_dir = os.path.dirname(os.path.abspath(world_dir))
        world_id = os.path.basename(os.path.abspath(world_dir))
        registry = WorldRegistry(base_dir=base_dir)
        bundle = registry.load_world(world_id)
        worker_manager.worlds[world_id] = bundle

    # Setup shared MessageHub
    worker_dir = os.path.join(os.path.expanduser("~"), ".agent-studio", "workers", "inline")
    msg_store = SQLiteMessageStore(worker_dir)
    message_hub = MessageHub(msg_store, None)

    for world_id, bundle in worker_manager.worlds.items():
        bus = bundle["event_bus_registry"].get_or_create(world_id)
        message_hub.register_world(world_id, bus, bundle.get("model_events", {}))
        bundle["instance_manager"]._message_hub = message_hub
        bundle["message_hub"] = message_hub

    # Start shared scenes for all loaded worlds
    for world_id, bundle in worker_manager.worlds.items():
        store = bundle["store"]
        sm = bundle["scene_manager"]
        scenes = store.list_scenes(world_id)
        for scene_data in scenes:
            if scene_data.get("mode") == "shared":
                scene_id = scene_data["scene_id"]
                refs = scene_data.get("refs", [])
                local_instances = scene_data.get("local_instances", {})
                sm.start(world_id, scene_id, mode="shared", references=refs, local_instances=local_instances)

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
        for world_id in list(worker_manager.worlds.keys()):
            try:
                worker_manager.handle_command("world.stop", {"world_id": world_id})
            except Exception:
                pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def _run():
        await message_hub.start()
        try:
            if supervisor_ws is not None:
                # WebSocket loopback connection to Supervisor
                from src.worker.cli.run_command import run_supervisor_client
                await run_supervisor_client(worker_manager, supervisor_ws)
            else:
                await asyncio.Event().wait()
        finally:
            await message_hub.stop()

    try:
        loop.run_until_complete(_run())
    finally:
        loop.close()

    return 0
