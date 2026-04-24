import asyncio
import os
import uuid
from datetime import datetime

from src.worker.server.jsonrpc_ws import JsonRpcError
from src.runtime.world_registry import WorldRegistry

_WORKER_ID_FILE = ".worker_id"


class WorkerManager:
    """Central coordinator inside each Worker process.

    Manages world_id -> bundle mapping, handles Supervisor commands,
    and sends periodic heartbeats.

    worker_id is persisted to {base_dir}/.worker_id so the Supervisor
    sees the same identity across Worker restarts.
    """

    def __init__(self, worker_id: str | None = None):
        self.worker_id = worker_id or str(uuid.uuid4())
        self.session_id = str(uuid.uuid4())
        self.worlds: dict[str, dict] = {}  # world_id -> bundle
        self._heartbeat_task: asyncio.Task | None = None
        self._base_dir: str | None = None

    def load_worlds(self, base_dir: str) -> list[str]:
        """Load all worlds found under base_dir and persist worker_id."""
        self._base_dir = os.path.abspath(base_dir)
        self._ensure_worker_id()

        registry = WorldRegistry(base_dir=self._base_dir)
        world_ids = registry.list_worlds()
        for world_id in world_ids:
            bundle = registry.load_world(world_id)
            self.worlds[world_id] = bundle
        return world_ids

    # ------------------------------------------------------------------
    # Worker ID persistence
    # ------------------------------------------------------------------

    def _ensure_worker_id(self) -> None:
        """Read or create the persistent worker_id file under base_dir."""
        if self._base_dir is None:
            return
        path = os.path.join(self._base_dir, _WORKER_ID_FILE)
        if os.path.isfile(path):
            try:
                with open(path, "r") as f:
                    stored = f.read().strip()
                if stored:
                    self.worker_id = stored
                    return
            except OSError:
                pass
        # Generate new worker_id and persist
        self.worker_id = str(uuid.uuid4())
        try:
            os.makedirs(self._base_dir, exist_ok=True)
            with open(path, "w") as f:
                f.write(self.worker_id + "\n")
        except OSError:
            pass  # Non-fatal: ephemeral worker_id is acceptable

    async def start_async(self) -> None:
        """Start background tasks for all loaded worlds (checkpoint loops)."""
        for bundle in self.worlds.values():
            state_mgr = bundle.get("state_manager")
            if state_mgr is not None and state_mgr._task is None:
                await state_mgr.start_async()

    def unload_world(self, world_id: str) -> bool:
        """Unload a single world and clean up resources."""
        bundle = self.worlds.pop(world_id, None)
        if bundle is None:
            return False

        # Stop MessageHub if present
        message_hub = bundle.get("message_hub")
        if message_hub is not None:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.run_coroutine_threadsafe(message_hub.stop(), loop)
                else:
                    loop.run_until_complete(message_hub.stop())
            except Exception:
                pass

        state_mgr = bundle["state_manager"]
        state_mgr.untrack_world(world_id)
        state_mgr.shutdown()

        store = bundle["store"]
        store.close()

        bus_reg = bundle["event_bus_registry"]
        bus_reg.destroy(world_id)

        world_lock = bundle["lock"]
        world_lock.release()

        return True

    async def handle_command(self, method: str, params: dict) -> dict:
        """Handle a command from Supervisor asynchronously.

        I/O-intensive operations (checkpoint, world loading, scene start/stop)
        are offloaded to a thread pool via asyncio.to_thread to avoid blocking
        the event loop. Lightweight in-memory operations run directly.
        """
        world_id = params.get("world_id")
        bundle = self.worlds.get(world_id) if world_id else None

        if method == "world.stop":
            if bundle is None:
                raise JsonRpcError(-32004, f"World {world_id} not loaded")
            force = params.get("force_stop_on_shutdown")
            await self._graceful_shutdown(bundle, force_stop_on_shutdown=force)
            self.worlds.pop(world_id, None)
            return {"status": "stopped"}

        if method == "world.checkpoint":
            if bundle is None:
                raise JsonRpcError(-32004, f"World {world_id} not loaded")
            await asyncio.to_thread(bundle["state_manager"].checkpoint_world, world_id)
            return {"status": "checkpointed"}

        if method == "world.getStatus":
            if bundle is None:
                raise JsonRpcError(-32004, f"World {world_id} not loaded")
            return {
                "world_id": world_id,
                "loaded": True,
                "scenes": [s["scene_id"] for s in bundle["scene_manager"].list_by_world(world_id)],
            }

        if method == "world.start":
            world_dir = params.get("world_dir")
            if world_dir is None:
                raise JsonRpcError(-32602, "world_dir required for world.start")
            base_dir = os.path.dirname(os.path.abspath(world_dir))
            registry = WorldRegistry(base_dir=base_dir)
            new_bundle = await asyncio.to_thread(registry.load_world, world_id)
            self.worlds[world_id] = new_bundle
            return {"status": "started"}

        if method == "world.reload":
            if bundle is None:
                raise JsonRpcError(-32004, f"World {world_id} not loaded")
            raise JsonRpcError(-32601, "world.reload not yet implemented")

        if method == "scene.start":
            if bundle is None:
                raise JsonRpcError(-32004, f"World {world_id} not loaded")
            scene_id = params.get("scene_id")
            if scene_id is None:
                raise JsonRpcError(-32602, "scene_id required")
            existing = bundle["scene_manager"].get(world_id, scene_id)
            if existing is not None:
                return {"status": "already_running"}
            await asyncio.to_thread(bundle["scene_manager"].start, world_id, scene_id, mode="isolated")
            return {"status": "started"}

        if method == "scene.stop":
            if bundle is None:
                raise JsonRpcError(-32004, f"World {world_id} not loaded")
            scene_id = params.get("scene_id")
            if scene_id is None:
                raise JsonRpcError(-32602, "scene_id required")
            ok = await asyncio.to_thread(bundle["scene_manager"].stop, world_id, scene_id)
            if not ok:
                raise JsonRpcError(-32002, "scene not found")
            return {"status": "stopped"}

        if method == "messageHub.publish":
            if bundle is None:
                raise JsonRpcError(-32004, f"World {world_id} not loaded")
            hub = bundle.get("message_hub")
            if hub is None:
                raise JsonRpcError(-32102, "message hub not initialized")
            hub.on_channel_message(
                params.get("event_type", ""),
                params.get("payload", {}),
                params.get("source", ""),
                params.get("scope", "world"),
                params.get("target"),
            )
            return {"acked": True}

        if method == "messageHub.publishBatch":
            if bundle is None:
                raise JsonRpcError(-32004, f"World {world_id} not loaded")
            hub = bundle.get("message_hub")
            if hub is None:
                raise JsonRpcError(-32102, "message hub not initialized")
            records = params.get("records", [])
            for record in records:
                hub.on_channel_message(
                    record.get("event_type", ""),
                    record.get("payload", {}),
                    record.get("source", ""),
                    record.get("scope", "world"),
                    record.get("target"),
                )
            return {"acked_ids": [r.get("id") for r in records]}

        raise JsonRpcError(-32601, f"Unknown method: {method}")

    async def _graceful_shutdown(self, bundle: dict, force_stop_on_shutdown: bool | None = None) -> None:
        world_id = bundle["world_id"]
        sm = bundle["scene_manager"]
        state_mgr = bundle["state_manager"]
        registry = bundle.get("_registry")

        if force_stop_on_shutdown is None:
            force_stop_on_shutdown = bundle.get("force_stop_on_shutdown", False)

        # 1. Stop isolated scenes
        isolated_scenes = [s for s in sm.list_by_world(world_id) if s.get("mode") == "isolated"]
        for scene in isolated_scenes:
            if not force_stop_on_shutdown:
                raise JsonRpcError(-32003, "isolated scenes are running and force_stop_on_shutdown is false")
            await asyncio.to_thread(sm.stop, world_id, scene["scene_id"])

        # 2. Stop shared scenes
        shared_scenes = [s for s in sm.list_by_world(world_id) if s.get("mode") == "shared"]
        for scene in shared_scenes:
            await asyncio.to_thread(sm.stop, world_id, scene["scene_id"])

        # 3. Stop MessageHub (already async, await directly)
        message_hub = bundle.get("message_hub")
        if message_hub is not None:
            try:
                await message_hub.stop()
            except Exception:
                pass

        # 4. Untrack and checkpoint
        state_mgr.untrack_world(world_id)
        await asyncio.to_thread(state_mgr.checkpoint_world, world_id)

        # 5. Unload world and release file lock
        if registry is not None:
            await asyncio.to_thread(registry.unload_world, world_id)
