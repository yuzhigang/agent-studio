import os
import yaml

from src.runtime.locks.world_lock import WorldLock
from src.runtime.stores.sqlite_store import SQLiteStore
from src.runtime.event_bus import EventBusRegistry
from src.runtime.instance_manager import InstanceManager
from src.runtime.scene_manager import SceneManager
from src.runtime.state_manager import StateManager


class WorldRegistry:
    def __init__(
        self,
        base_dir: str = "worlds",
        metric_store_factory=None,
    ):
        self._base_dir = base_dir
        self._metric_store_factory = metric_store_factory
        self._loaded: dict[str, dict] = {}

    def _world_dir(self, world_id: str) -> str:
        return os.path.join(self._base_dir, world_id)

    def create_world(self, world_id: str, config: dict | None = None) -> dict:
        config = config or {}
        world_dir = self._world_dir(world_id)
        os.makedirs(world_dir, exist_ok=True)
        os.makedirs(os.path.join(world_dir, "scenes"), exist_ok=True)
        os.makedirs(os.path.join(world_dir, "resources"), exist_ok=True)

        world_yaml = {
            "world_id": world_id,
            "name": config.get("name", world_id),
            "description": config.get("description", ""),
            "config": config,
        }
        yaml_path = os.path.join(world_dir, "world.yaml")
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(world_yaml, f, allow_unicode=True, sort_keys=False)

        store = SQLiteStore(world_dir)
        store.save_world(world_id, config)
        store.close()

        return world_yaml

    def load_world(self, world_id: str) -> dict:
        if world_id in self._loaded:
            return self._loaded[world_id]

        world_dir = self._world_dir(world_id)
        if not os.path.isdir(world_dir):
            raise ValueError(f"World {world_id} not found")

        yaml_path = os.path.join(world_dir, "world.yaml")
        if not os.path.exists(yaml_path):
            raise ValueError(f"World {world_id} has no world.yaml")

        world_lock = WorldLock(world_dir)
        world_lock.acquire()

        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                world_yaml = yaml.safe_load(f)

            store = SQLiteStore(world_dir)
            store.save_world(world_id, world_yaml.get("config", {}))

            bus_reg = EventBusRegistry()
            im = InstanceManager(bus_reg, instance_store=store)
            scene_mgr = SceneManager(im, bus_reg, scene_store=store)
            metric_store = (
                self._metric_store_factory(world_id)
                if self._metric_store_factory
                else None
            )
            state_mgr = StateManager(
                im,
                scene_mgr,
                store,
                store,
                store,
                metric_store=metric_store,
            )
            scene_mgr._state_manager = state_mgr

            state_mgr.restore_world(world_id)
            state_mgr.track_world(world_id)

            bundle = {
                "world_id": world_id,
                "world_yaml": world_yaml,
                "store": store,
                "event_bus_registry": bus_reg,
                "instance_manager": im,
                "scene_manager": scene_mgr,
                "state_manager": state_mgr,
                "metric_store": metric_store,
                "lock": world_lock,
                "_registry": self,
                "force_stop_on_shutdown": False,
            }
            self._loaded[world_id] = bundle
            return bundle
        except Exception:
            world_lock.release()
            raise

    def unload_world(self, world_id: str) -> bool:
        bundle = self._loaded.pop(world_id, None)
        if bundle is None:
            return False

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

    def list_worlds(self) -> list[str]:
        if not os.path.isdir(self._base_dir):
            return []
        return [
            name
            for name in os.listdir(self._base_dir)
            if os.path.isdir(os.path.join(self._base_dir, name))
            and os.path.exists(os.path.join(self._base_dir, name, "world.yaml"))
        ]

    def get_loaded_world(self, world_id: str) -> dict | None:
        return self._loaded.get(world_id)
