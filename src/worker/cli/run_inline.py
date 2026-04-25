import os
import signal
import sys

from src.runtime.world_registry import WorldRegistry
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
    message_hub = worker_manager.build_message_hub(worker_dir=worker_dir, channel=None)

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

    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    main_fut: asyncio.Future | None = None

    def _shutdown(signum, frame):
        print("Shutting down inline runtime...")
        loop.call_soon_threadsafe(lambda: asyncio.ensure_future(_shutdown_all()))

    async def _shutdown_all():
        for world_id in list(worker_manager.worlds.keys()):
            try:
                await worker_manager.handle_command("world.remove", {"world_id": world_id})
            except Exception:
                pass
        if main_fut is not None and not main_fut.done():
            main_fut.cancel()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    async def _run():
        nonlocal main_fut
        await message_hub.start()
        await worker_manager.start_async()
        main_fut = asyncio.Future()
        try:
            if supervisor_ws is not None:
                # WebSocket loopback connection to Supervisor
                from src.worker.cli.run_command import run_supervisor_client
                await run_supervisor_client(worker_manager, supervisor_ws)
            else:
                await main_fut
        finally:
            await message_hub.stop()

    try:
        loop.run_until_complete(_run())
    finally:
        loop.close()

    return 0
