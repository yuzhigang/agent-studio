import copy
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
        for ref_id in references:
            inst = self._im.get(project_id, ref_id, scope="project")
            if inst is None:
                raise ValueError(f"Referenced instance {ref_id} not found in project {project_id}")
            for link_target in (inst.links or {}).values():
                if link_target and link_target not in resolved_refs:
                    linked = self._im.get(project_id, link_target, scope="project")
                    if linked is not None and len(resolved_refs) < len(references) + 2:
                        resolved_refs.append(link_target)

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
        if mode == "isolated":
            scene_instances = self._im.list_by_scope(project_id, f"scene:{scene_id}")
            self._backfill_metrics(project_id, scene_id, scene_instances)

        # Property reconciliation must happen after metric backfill (spec 7.1 step 5)
        all_scene_instances = self._im.list_by_scope(project_id, f"scene:{scene_id}")
        self._reconcile_properties(all_scene_instances)

        self._scenes[(project_id, scene_id)] = scene
        return scene

    def stop(self, project_id: str, scene_id: str) -> bool:
        key = (project_id, scene_id)
        scene = self._scenes.pop(key, None)
        if scene is None:
            return False
        bus = self._bus_reg.get_or_create(project_id)
        # Unregister scene-scoped instances from event bus
        for inst in self._im.list_by_scope(project_id, f"scene:{scene_id}"):
            bus.unregister(inst.id)
            self._im.remove(project_id, inst.id, scope=inst.scope)
        return True

    def get(self, project_id: str, scene_id: str) -> dict | None:
        return self._scenes.get((project_id, scene_id))
