import asyncio
import os
import signal

from src.worker.channels.supervisor_connection import SupervisorConnection
from src.worker.manager import WorkerManager
from src.worker.server.jsonrpc_ws import JsonRpcError


def run_world(base_dir, supervisor_ws=None, ws_port=None, force_stop_on_shutdown=None):
    base_dir = os.path.abspath(base_dir)

    # WorkerManager loads all worlds in the base directory
    worker_manager = WorkerManager()
    world_ids = worker_manager.load_worlds(base_dir)

    # Apply force_stop_on_shutdown override if provided
    if force_stop_on_shutdown is not None:
        for bundle in worker_manager.worlds.values():
            bundle["force_stop_on_shutdown"] = force_stop_on_shutdown

    # Create worker-level MessageHub and register all worlds.
    # SupervisorConnection owns the single WebSocket to Supervisor,
    # handling both Channel protocol (message routing) and worker
    # lifecycle (registration, heartbeats, command dispatch).
    worker_dir = os.path.join(
        os.path.expanduser("~"), ".agent-studio", "workers", str(os.getpid())
    )
    channel = (
        SupervisorConnection(supervisor_ws, worker_manager) if supervisor_ws else None
    )
    message_hub = worker_manager.build_message_hub(
        worker_dir=worker_dir, channel=channel
    )

    # Start shared scenes for all loaded worlds
    for bundle in worker_manager.worlds.values():
        _start_shared_scenes(bundle)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    main_fut: asyncio.Future | None = None

    # ---- Signal handling ----

    def _on_signal(signum, frame):
        print(f"Received signal {signum}, shutting down...")
        loop.call_soon_threadsafe(lambda: asyncio.ensure_future(_shutdown_all()))

    async def _shutdown_all():
        for world_id in list(worker_manager.worlds.keys()):
            try:
                await worker_manager.handle_command(
                    "world.remove", {"world_id": world_id}
                )
            except JsonRpcError as e:
                print(f"Shutdown aborted for {world_id}: {e.message}")
                return
            except Exception:
                pass
        if main_fut is not None and not main_fut.done():
            main_fut.cancel()

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    tasks = []

    async def _start_and_run():
        nonlocal main_fut
        await message_hub.start()
        main_fut = asyncio.Future()
        try:
            await main_fut
        finally:
            await message_hub.stop()

    async def _start_state_managers():
        await worker_manager.start_async()

    tasks.append(loop.create_task(_start_and_run()))
    tasks.append(loop.create_task(_start_state_managers()))

    try:
        loop.run_until_complete(asyncio.gather(*tasks))
    finally:
        loop.close()

    return 0


def _start_shared_scenes(bundle):
    WorkerManager._start_shared_scenes_for_bundle(bundle)


def _graceful_shutdown(bundle, force_stop_on_shutdown=None):
    world_id = bundle["world_id"]
    sm = bundle["scene_manager"]
    state_mgr = bundle["state_manager"]
    registry = bundle.get("_registry")

    if force_stop_on_shutdown is None:
        force_stop_on_shutdown = bundle.get("force_stop_on_shutdown", False)

    # 1. Stop isolated scenes
    isolated_scenes = [
        s for s in sm.list_by_world(world_id) if s.get("mode") == "isolated"
    ]
    for scene in isolated_scenes:
        if not force_stop_on_shutdown:
            raise JsonRpcError(
                -32003,
                "isolated scenes are running and force_stop_on_shutdown is false",
            )
        sm.stop(world_id, scene["scene_id"])

    # 2. Stop shared scenes
    shared_scenes = [s for s in sm.list_by_world(world_id) if s.get("mode") == "shared"]
    for scene in shared_scenes:
        sm.stop(world_id, scene["scene_id"])

    message_hub = bundle.get("message_hub")
    if message_hub is not None:
        message_hub.unregister_world(world_id, permanent=True)

    # 4. Untrack and checkpoint
    state_mgr.untrack_world(world_id)
    state_mgr.checkpoint_world(world_id)

    # 5. Unload world and release file lock
    if registry is not None:
        registry.unload_world(world_id)
