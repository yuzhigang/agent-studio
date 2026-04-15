import threading
import time
from datetime import datetime, timezone

from src.runtime.instance_manager import InstanceManager
from src.runtime.scene_manager import SceneManager


class StateManager:
    def __init__(
        self,
        instance_manager: InstanceManager,
        scene_manager: SceneManager | None,
        instance_store,
        scene_store,
        event_log_store,
        metric_store=None,
    ):
        self._im = instance_manager
        self._sm = scene_manager
        self._instance_store = instance_store
        self._scene_store = scene_store
        self._event_log_store = event_log_store
        self._metric_store = metric_store
        self._loaded_projects: set[str] = set()
        self._loaded_lock = threading.Lock()
        self._project_locks: dict[str, threading.Lock] = {}
        self._project_locks_lock = threading.Lock()
        self._shutdown = False
        self._thread = threading.Thread(target=self._auto_checkpoint_loop, daemon=True)
        self._thread.start()

    def _get_project_lock(self, project_id: str) -> threading.Lock:
        with self._project_locks_lock:
            if project_id not in self._project_locks:
                self._project_locks[project_id] = threading.Lock()
            return self._project_locks[project_id]

    def track_project(self, project_id: str) -> None:
        with self._loaded_lock:
            self._loaded_projects.add(project_id)

    def untrack_project(self, project_id: str) -> None:
        with self._loaded_lock:
            self._loaded_projects.discard(project_id)

    def _auto_checkpoint_loop(self) -> None:
        while not self._shutdown:
            time.sleep(30)
            if self._shutdown:
                break
            with self._loaded_lock:
                projects = list(self._loaded_projects)
            for project_id in projects:
                lock = self._get_project_lock(project_id)
                acquired = lock.acquire(blocking=False)
                if not acquired:
                    continue
                try:
                    self.checkpoint_project(project_id)
                except Exception:
                    # Swallow errors in background thread
                    pass
                finally:
                    lock.release()

    def checkpoint_project(self, project_id: str, last_event_id: str | None = None) -> None:
        lock = self._get_project_lock(project_id)
        with lock:
            instances = self._im.list_by_project(project_id)
            for inst in instances:
                if inst.lifecycle_state in ("active", "completed"):
                    snapshot = self._im.snapshot(inst)
                    self._instance_store.save_instance(
                        project_id, inst.id, inst.scope, snapshot
                    )
            now = datetime.now(timezone.utc).isoformat()
            if hasattr(self._instance_store, "save_project_state"):
                self._instance_store.save_project_state(project_id, last_event_id, now)

    def restore_project(self, project_id: str) -> bool:
        # Load active and completed instances into memory
        for state in ("active", "completed"):
            snapshots = self._instance_store.list_instances(
                project_id, lifecycle_state=state
            )
            for snap in snapshots:
                self._im.get(project_id, snap["instance_id"], snap["scope"])

        # Replay events after last checkpoint
        last_event_id = None
        if hasattr(self._instance_store, "load_project_state"):
            ps = self._instance_store.load_project_state(project_id)
            if ps is not None:
                last_event_id = ps.get("last_event_id")

        events = self._event_log_store.replay_after(project_id, last_event_id)
        bus = None
        if self._im._bus_reg is not None:
            bus = self._im._bus_reg.get_or_create(project_id)
        for evt in events:
            if bus is not None:
                bus.publish(
                    evt["event_type"],
                    evt["payload"],
                    evt["source"],
                    evt["scope"],
                )

        # Metric backfill
        if self._metric_store is not None:
            for inst in self._im.list_by_project(project_id):
                model = inst.model or {}
                for name, var_def in (model.get("variables") or {}).items():
                    if var_def.get("x-category") == "metric":
                        last = self._metric_store.latest(project_id, inst.id, name)
                        if last is not None:
                            inst.variables[name] = last

        # Property reconciliation
        if self._sm is not None:
            self._sm._reconcile_properties(self._im.list_by_project(project_id))

        return True

    def checkpoint_scene(
        self, project_id: str, scene_id: str, last_event_id: str | None = None
    ) -> None:
        lock = self._get_project_lock(project_id)
        with lock:
            scene_instances = self._im.list_by_scope(project_id, f"scene:{scene_id}")
            for inst in scene_instances:
                snapshot = self._im.snapshot(inst)
                self._instance_store.save_instance(
                    project_id, inst.id, inst.scope, snapshot
                )
            scene = self._sm.get(project_id, scene_id) if self._sm else None
            if scene is not None and self._scene_store is not None:
                scene_data = {
                    "mode": scene["mode"],
                    "refs": scene["references"],
                    "local_instances": scene["local_instances"],
                    "last_event_id": last_event_id,
                    "checkpointed_at": datetime.now(timezone.utc).isoformat(),
                }
                self._scene_store.save_scene(project_id, scene_id, scene_data)

    def restore_scene(self, project_id: str, scene_id: str) -> dict | None:
        if self._scene_store is None:
            return None
        scene_data = self._scene_store.load_scene(project_id, scene_id)
        if scene_data is None:
            return None

        # Load scene-scoped instances into memory
        snapshots = self._instance_store.list_instances(
            project_id, scope=f"scene:{scene_id}"
        )
        for snap in snapshots:
            self._im.get(project_id, snap["instance_id"], snap["scope"])

        # Register scene in SceneManager memory
        scene = {
            "project_id": project_id,
            "scene_id": scene_id,
            "mode": scene_data["mode"],
            "references": scene_data["refs"],
            "local_instances": scene_data["local_instances"],
        }
        if self._sm is not None:
            self._sm._scenes[(project_id, scene_id)] = scene

        # Metric backfill and property reconciliation
        scene_instances = self._im.list_by_scope(project_id, f"scene:{scene_id}")
        if self._sm is not None:
            self._sm._backfill_metrics(project_id, scene_id, scene_instances)
            self._sm._reconcile_properties(scene_instances)

        return scene

    def shutdown(self) -> None:
        self._shutdown = True
        self._thread.join(timeout=5)
