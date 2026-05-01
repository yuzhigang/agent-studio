import asyncio
import os
import signal
import sys

from src.runtime.world_registry import WorldRegistry
from src.worker.channels.supervisor_connection import SupervisorConnection
from src.worker.manager import WorkerManager


def run_inline(world_dirs, supervisor_ws=None):
    if not world_dirs:
        return 0

    worker_manager = WorkerManager()

    # Group worlds by base_dir so worlds in the same directory share one registry
    # (matching run_world behavior), while worlds in different directories each
    # get their own registry.
    from collections import defaultdict

    groups: dict[str, list[str]] = defaultdict(list)
    for world_dir in world_dirs:
        base_dir = os.path.dirname(os.path.abspath(world_dir))
        groups[base_dir].append(world_dir)

    for base_dir, dirs in groups.items():
        registry = WorldRegistry(base_dir=base_dir)
        for world_dir in dirs:
            world_id = os.path.basename(os.path.abspath(world_dir))
            bundle = registry.load_world(world_id)
            worker_manager.worlds[world_id] = bundle

    # Setup shared MessageHub.
    # SupervisorConnection owns the single WebSocket to Supervisor,
    # handling both Channel protocol (message routing) and worker
    # lifecycle (registration, heartbeats, command dispatch).
    worker_dir = os.path.join(
        os.path.expanduser("~"), ".agent-studio", "workers", "inline"
    )
    channel = (
        SupervisorConnection(supervisor_ws, worker_manager) if supervisor_ws else None
    )
    message_hub = worker_manager.build_message_hub(
        worker_dir=worker_dir, channel=channel
    )

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
                sm.start(
                    world_id,
                    scene_id,
                    mode="shared",
                    references=refs,
                    local_instances=local_instances,
                )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    shutdown_event = asyncio.Event()

    def _shutdown(signum, frame):
        print("Shutting down inline runtime...")
        loop.call_soon_threadsafe(shutdown_event.set)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    async def _cleanup():
        for world_id in list(worker_manager.worlds.keys()):
            try:
                await worker_manager.handle_command(
                    "world.remove", {"world_id": world_id}
                )
            except Exception:
                pass

    async def _check_supervisor(ws_url: str, timeout: float = 3.0):
        """Verify supervisor is reachable before entering the main loop.

        Fails fast with a clear error message instead of silently retrying
        in the background.
        """
        import websockets

        try:
            async with asyncio.timeout(timeout):
                async with websockets.connect(ws_url):
                    pass  # Just probing connectivity
        except asyncio.TimeoutError:
            print(
                f"Supervisor unreachable at {ws_url}: connection timed out after {timeout}s"
            )
            print("Start the supervisor first: agent-studio supervisor")
            sys.exit(1)
        except (OSError, websockets.exceptions.InvalidURI) as e:
            print(f"Supervisor unreachable at {ws_url}: {e}")
            print("Start the supervisor first: agent-studio supervisor")
            sys.exit(1)

    async def _run():
        # Pre-connect check: fail fast if supervisor is configured but unreachable
        if supervisor_ws:
            await _check_supervisor(supervisor_ws)

        await message_hub.start()
        await worker_manager.start_async()

        try:
            await shutdown_event.wait()
        finally:
            await _cleanup()
            await message_hub.stop()

    try:
        loop.run_until_complete(_run())
    finally:
        loop.close()

    return 0
