import copy
import threading
from collections import deque
from src.runtime.instance_manager import InstanceManager
from src.runtime.event_bus import EventBusRegistry


class SceneController:
    def __init__(
        self,
        instance_manager: InstanceManager,
        event_bus_registry: EventBusRegistry,
        metric_store=None,
    ):
        self._im = instance_manager
        self._bus_reg = event_bus_registry
        self._metric_store = metric_store
        self._scenes: dict[tuple[str, str], dict] = {}
        self._scene_lock = threading.Lock()

    def _backfill_metrics(self, project_id: str, scene_id: str, instances: list):
        """Stub metric backfill: in a real system queries the time-series DB."""
        if self._metric_store is None:
            return
        for inst in instances:
            model = inst.model or {}
            for name, var_def in (model.get("variables") or {}).items():
                if var_def.get("x-category") == "metric":
                    last = self._metric_store.latest(project_id, inst.id, name)
                    if last is not None:
                        inst.variables[name] = last

    def _reconcile_properties(self, instances: list):
        """Stub property reconciliation: derivedProperties will be recomputed here."""
        # TODO: recompute derivedProperties based on current variables/attributes
        pass

    def start(
        self,
        project_id: str,
        scene_id: str,
        mode: str,
        references: list[str] | None = None,
        local_instances: dict | None = None,
    ) -> dict:
        references = references or []
        local_instances = local_instances or {}
        if mode not in ("shared", "isolated"):
            raise ValueError(f"Invalid scene mode: {mode}")

        # Reference validation + auto-pull (depth <= 2)
        resolved_refs = list(references)
        queue = deque([(ref_id, 0) for ref_id in references])
        seen = set(references)
        while queue:
            current_id, depth = queue.popleft()
            if depth >= 2:
                continue
            inst = self._im.get(project_id, current_id, scope="project")
            if inst is None:
                if current_id in references:
                    raise ValueError(f"Referenced instance {current_id} not found in project {project_id}")
                continue
            for link_target in (inst.links or {}).values():
                if link_target and link_target not in seen:
                    seen.add(link_target)
                    linked = self._im.get(project_id, link_target, scope="project")
                    if linked is not None:
                        resolved_refs.append(link_target)
                        queue.append((link_target, depth + 1))

        scene = {
            "project_id": project_id,
            "scene_id": scene_id,
            "mode": mode,
            "references": resolved_refs,
            "local_instances": {},
        }

        if mode == "isolated":
            for ref_id in resolved_refs:
                self._im.copy_for_scene(project_id, ref_id, scene_id)

        for local_id, local_spec in local_instances.items():
            local_inst = self._im.create(
                project_id=project_id,
                model_name=local_spec["modelName"],
                instance_id=local_id,
                scope=f"scene:{scene_id}",
                variables=copy.deepcopy(local_spec.get("variables", {})),
            )
            scene["local_instances"][local_id] = local_inst.id

        # Metric backfill for isolated scenes (spec 6.3 / 7.1 step 3)
        actual_scene_instances: list = []
        if mode == "isolated":
            for ref_id in resolved_refs:
                actual_scene_instances.append(self._im.get(project_id, ref_id, scope=f"scene:{scene_id}"))
        for local_id in local_instances:
            actual_scene_instances.append(self._im.get(project_id, local_id, scope=f"scene:{scene_id}"))

        # Property reconciliation must happen after metric backfill (spec 7.1 step 5)
        actual_scene_instances = [i for i in actual_scene_instances if i is not None]

        if mode == "isolated":
            self._backfill_metrics(project_id, scene_id, actual_scene_instances)

        # Property reconciliation must happen after metric backfill (spec 7.1 step 5)
        self._reconcile_properties(actual_scene_instances)

        with self._scene_lock:
            self._scenes[(project_id, scene_id)] = scene
        return scene

    def stop(self, project_id: str, scene_id: str) -> bool:
        key = (project_id, scene_id)
        with self._scene_lock:
            scene = self._scenes.pop(key, None)
        if scene is None:
            return False
        for inst in self._im.list_by_scope(project_id, f"scene:{scene_id}"):
            self._im.remove(project_id, inst.id, scope=inst.scope)
        return True

    def get(self, project_id: str, scene_id: str) -> dict | None:
        with self._scene_lock:
            return self._scenes.get((project_id, scene_id))
