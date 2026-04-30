import asyncio
import os
import uuid
from datetime import datetime

from src.runtime.messaging import MessageEnvelope, MessageHub
from src.runtime.messaging.sqlite_store import SQLiteMessageStore
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
        self._message_hub: MessageHub | None = None

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

    def build_message_hub(self, worker_dir: str, channel) -> MessageHub:
        if self._message_hub is None:
            store = SQLiteMessageStore(worker_dir)
            self._message_hub = MessageHub(store, channel, poll_interval=0.05)
        elif channel is not None and self._message_hub._channel is not channel:
            raise RuntimeError("MessageHub already exists with a different channel binding")

        for world_id, bundle in self.worlds.items():
            self._bind_world_bundle(world_id, bundle)

        return self._message_hub

    def _bind_world_bundle(self, world_id: str, bundle: dict) -> None:
        if self._message_hub is None:
            return
        receiver = bundle.get("message_receiver")
        if receiver is not None:
            self._message_hub.register_world(world_id, receiver)
        sender = bundle.get("message_sender")
        if sender is not None:
            sender.bind_hub(self._message_hub)
        bundle["message_hub"] = self._message_hub

    @staticmethod
    def _message_envelope_from_params(
        params: dict,
        *,
        default_target_world: str | None = None,
    ) -> MessageEnvelope:
        target_world = params.get("target_world", default_target_world)
        if not target_world:
            raise JsonRpcError(-32602, "target_world required")
        return MessageEnvelope(
            message_id=params.get("message_id") or params.get("id") or str(uuid.uuid4()),
            source_world=params.get("source_world"),
            target_world=target_world,
            event_type=params.get("event_type", ""),
            payload=params.get("payload", {}),
            source=params.get("source"),
            scope=params.get("scope", "world"),
            target=params.get("target"),
            trace_id=params.get("trace_id"),
            headers=params.get("headers") or {},
        )

    def unload_world(self, world_id: str) -> bool:
        """Unload a single world and clean up resources."""
        bundle = self.worlds.pop(world_id, None)
        if bundle is None:
            return False

        if self._message_hub is not None:
            self._message_hub.unregister_world(world_id, permanent=True)

        registry = bundle.get("_registry")
        if registry is not None:
            loaded_bundle = registry.get_loaded_world(world_id)
            if loaded_bundle is not None:
                return registry.unload_world(world_id)

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

    @staticmethod
    def _start_shared_scenes_for_bundle(bundle: dict) -> None:
        store = bundle["store"]
        sm = bundle["scene_manager"]
        world_id = bundle["world_id"]
        scenes = store.list_scenes(world_id)
        for scene_data in scenes:
            if scene_data.get("mode") == "shared":
                scene_id = scene_data["scene_id"]
                if sm.get(world_id, scene_id) is not None:
                    continue
                refs = scene_data.get("refs", [])
                local_instances = scene_data.get("local_instances", {})
                sm.start(
                    world_id,
                    scene_id,
                    mode="shared",
                    references=refs,
                    local_instances=local_instances,
                )

    async def handle_command(self, method: str, params: dict) -> dict:
        """Dispatch a command to the appropriate handler."""
        from src.worker.commands import get_handler

        handler = get_handler(method)
        if handler is None:
            raise JsonRpcError(-32601, f"Unknown method: {method}")

        world_id = params.get("world_id")
        bundle = self.worlds.get(world_id) if world_id else None
        return await handler(self, bundle, params)

    async def _graceful_shutdown(
        self,
        bundle: dict,
        force_stop_on_shutdown: bool | None = None,
        *,
        permanent: bool = False,
    ) -> None:
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

        if self._message_hub is not None:
            self._message_hub.unregister_world(world_id, permanent=permanent)

        # 3. Untrack and checkpoint
        state_mgr.untrack_world(world_id)
        await asyncio.to_thread(state_mgr.checkpoint_world, world_id)
        state_mgr.shutdown()
        bundle["runtime_status"] = "stopped"

        # 4. Unload world and release file lock
        if permanent and registry is not None:
            await asyncio.to_thread(registry.unload_world, world_id)
