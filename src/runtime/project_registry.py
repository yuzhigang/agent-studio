import os
import yaml

from src.runtime.locks.project_lock import ProjectLock
from src.runtime.stores.sqlite_store import SQLiteStore
from src.runtime.event_bus import EventBusRegistry
from src.runtime.instance_manager import InstanceManager
from src.runtime.scene_manager import SceneManager
from src.runtime.state_manager import StateManager


class ProjectRegistry:
    def __init__(
        self,
        base_dir: str = "projects",
        metric_store_factory=None,
    ):
        self._base_dir = base_dir
        self._metric_store_factory = metric_store_factory
        self._loaded: dict[str, dict] = {}

    def _project_dir(self, project_id: str) -> str:
        return os.path.join(self._base_dir, project_id)

    def create_project(self, project_id: str, config: dict | None = None) -> dict:
        config = config or {}
        project_dir = self._project_dir(project_id)
        os.makedirs(project_dir, exist_ok=True)
        os.makedirs(os.path.join(project_dir, "scenes"), exist_ok=True)
        os.makedirs(os.path.join(project_dir, "resources"), exist_ok=True)

        project_yaml = {
            "project_id": project_id,
            "name": config.get("name", project_id),
            "description": config.get("description", ""),
            "config": config,
        }
        yaml_path = os.path.join(project_dir, "project.yaml")
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(project_yaml, f, allow_unicode=True, sort_keys=False)

        store = SQLiteStore(project_dir)
        store.save_project(project_id, config)
        store.close()

        return project_yaml

    def load_project(self, project_id: str) -> dict:
        if project_id in self._loaded:
            return self._loaded[project_id]

        project_dir = self._project_dir(project_id)
        if not os.path.isdir(project_dir):
            raise ValueError(f"Project {project_id} not found")

        yaml_path = os.path.join(project_dir, "project.yaml")
        if not os.path.exists(yaml_path):
            raise ValueError(f"Project {project_id} has no project.yaml")

        project_lock = ProjectLock(project_dir)
        project_lock.acquire()

        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                project_yaml = yaml.safe_load(f)

            store = SQLiteStore(project_dir)
            store.save_project(project_id, project_yaml.get("config", {}))

            bus_reg = EventBusRegistry()
            im = InstanceManager(bus_reg, instance_store=store)
            scene_mgr = SceneManager(im, bus_reg, scene_store=store)
            metric_store = (
                self._metric_store_factory(project_id)
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

            state_mgr.restore_project(project_id)
            state_mgr.track_project(project_id)

            bundle = {
                "project_id": project_id,
                "project_yaml": project_yaml,
                "store": store,
                "event_bus_registry": bus_reg,
                "instance_manager": im,
                "scene_manager": scene_mgr,
                "state_manager": state_mgr,
                "metric_store": metric_store,
                "lock": project_lock,
                "_registry": self,
                "force_stop_on_shutdown": False,
            }
            self._loaded[project_id] = bundle
            return bundle
        except Exception:
            project_lock.release()
            raise

    def unload_project(self, project_id: str) -> bool:
        bundle = self._loaded.pop(project_id, None)
        if bundle is None:
            return False

        state_mgr = bundle["state_manager"]
        state_mgr.untrack_project(project_id)
        state_mgr.shutdown()

        store = bundle["store"]
        store.close()

        bus_reg = bundle["event_bus_registry"]
        bus_reg.destroy(project_id)

        project_lock = bundle["lock"]
        project_lock.release()

        return True

    def list_projects(self) -> list[str]:
        if not os.path.isdir(self._base_dir):
            return []
        return [
            name
            for name in os.listdir(self._base_dir)
            if os.path.isdir(os.path.join(self._base_dir, name))
            and os.path.exists(os.path.join(self._base_dir, name, "project.yaml"))
        ]

    def get_loaded_project(self, project_id: str) -> dict | None:
        return self._loaded.get(project_id)
