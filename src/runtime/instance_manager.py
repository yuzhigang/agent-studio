import threading
import copy
import functools
from datetime import datetime, timezone
from typing import Callable

from src.runtime.instance import Instance


class InstanceManager:
    def __init__(
        self,
        event_bus_registry=None,
        instance_store=None,
        model_loader: Callable[[str], dict | None] | None = None,
    ):
        self._instances: dict[tuple[str, str], Instance] = {}
        self._lock = threading.Lock()
        self._bus_reg = event_bus_registry
        self._store = instance_store
        self._model_loader = model_loader

    @staticmethod
    def _make_key(project_id: str, instance_id: str, scope: str = "project") -> tuple[str, str]:
        if scope.startswith("scene:"):
            scene_id = scope.split(":", 1)[1]
            return (project_id, f"{instance_id}@scene:{scene_id}")
        return (project_id, instance_id)

    def _on_event(self, instance: Instance, event_type: str, payload: dict, source: str):
        # TODO: wire behavior execution via SandboxExecutor in a future iteration
        pass

    def _register_instance(self, inst: Instance):
        if self._bus_reg is None:
            return
        bus = self._bus_reg.get_or_create(inst.project_id)
        model = inst.model or {}
        behaviors = model.get("behaviors") or {}
        event_types = set()
        for b in behaviors.values():
            trigger = b.get("trigger", {})
            if trigger.get("type") == "event":
                event_types.add(trigger.get("name"))
        if not event_types:
            event_types.add("__noop__")
        for et in event_types:
            bus.register(inst.id, inst.scope, et, functools.partial(self._on_event, inst))

    def _unregister_instance(self, inst: Instance):
        if self._bus_reg is None:
            return
        bus = self._bus_reg.get_or_create(inst.project_id)
        bus.unregister(inst.id)

    def snapshot(self, inst: Instance) -> dict:
        return {
            "model_name": inst.model_name,
            "model_version": inst.model_version,
            "attributes": inst.attributes or {},
            "state": inst.state or {"current": None, "enteredAt": None},
            "variables": inst.variables or {},
            "links": inst.links or {},
            "memory": inst.memory or {},
            "audit": inst.audit or {"version": 0, "updatedAt": None, "lastEventId": None},
            "lifecycle_state": inst.lifecycle_state,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _save_to_store(self, inst: Instance):
        if self._store is not None:
            self._store.save_instance(
                inst.project_id, inst.instance_id, inst.scope, self.snapshot(inst)
            )

    def create(
        self,
        project_id: str,
        model_name: str,
        instance_id: str,
        scope: str = "project",
        model_version: str | None = None,
        attributes: dict | None = None,
        variables: dict | None = None,
        links: dict | None = None,
        memory: dict | None = None,
        state: dict | None = None,
        model: dict | None = None,
    ) -> Instance:
        attributes = attributes or {}
        variables = variables or {}
        links = links or {}
        memory = memory or {}
        state = state or {"current": None, "enteredAt": None}
        inst = Instance(
            instance_id=instance_id,
            model_name=model_name,
            project_id=project_id,
            scope=scope,
            model_version=model_version,
            attributes=copy.deepcopy(attributes),
            variables=copy.deepcopy(variables),
            links=copy.deepcopy(links),
            memory=copy.deepcopy(memory),
            state=copy.deepcopy(state),
            model=copy.deepcopy(model) if model is not None else None,
        )
        key = self._make_key(project_id, instance_id, scope)
        with self._lock:
            if key in self._instances:
                raise ValueError(f"Instance {instance_id} already exists in project {project_id} with scope {scope}")
            self._instances[key] = inst
            try:
                self._register_instance(inst)
            except Exception:
                self._instances.pop(key, None)
                raise
        self._save_to_store(inst)
        return inst

    def get(self, project_id: str, instance_id: str, scope: str = "project") -> Instance | None:
        key = self._make_key(project_id, instance_id, scope)
        with self._lock:
            inst = self._instances.get(key)
            if inst is not None:
                return inst
            if self._store is None:
                return None
            snapshot = self._store.load_instance(project_id, instance_id, scope)
            if snapshot is None:
                return None
            inst = Instance(
                instance_id=snapshot["instance_id"],
                model_name=snapshot["model_name"],
                project_id=snapshot["project_id"],
                scope=snapshot["scope"],
                model_version=snapshot.get("model_version"),
                attributes=copy.deepcopy(snapshot.get("attributes", {})),
                variables=copy.deepcopy(snapshot.get("variables", {})),
                links=copy.deepcopy(snapshot.get("links", {})),
                memory=copy.deepcopy(snapshot.get("memory", {})),
                state=copy.deepcopy(snapshot.get("state", {"current": None, "enteredAt": None})),
                audit=copy.deepcopy(snapshot.get("audit", {"version": 0, "updatedAt": None, "lastEventId": None})),
                lifecycle_state=snapshot.get("lifecycle_state", "active"),
            )
            if self._model_loader is not None:
                loaded_model = self._model_loader(inst.model_name)
                if loaded_model is not None:
                    inst.model = loaded_model
            self._instances[key] = inst
            try:
                self._register_instance(inst)
            except Exception:
                self._instances.pop(key, None)
                raise
            return inst

    def list_by_project(self, project_id: str) -> list[Instance]:
        with self._lock:
            return [inst for (pid, _), inst in self._instances.items() if pid == project_id]

    def list_by_scope(self, project_id: str, scope: str) -> list[Instance]:
        with self._lock:
            return [
                inst for (pid, _), inst in self._instances.items()
                if pid == project_id and inst.scope == scope
            ]

    def remove(self, project_id: str, instance_id: str, scope: str = "project") -> bool:
        key = self._make_key(project_id, instance_id, scope)
        with self._lock:
            inst = self._instances.pop(key, None)
        if inst is not None:
            self._unregister_instance(inst)
            if self._store is not None:
                self._store.delete_instance(project_id, instance_id, scope)
            return True
        return False

    def transition_lifecycle(self, project_id: str, instance_id: str, new_state: str, scope: str = "project") -> bool:
        inst = self.get(project_id, instance_id, scope)
        if inst is None:
            return False
        inst.lifecycle_state = new_state
        self._save_to_store(inst)
        if new_state == "archived":
            with self._lock:
                self._instances.pop(self._make_key(project_id, instance_id, scope), None)
            self._unregister_instance(inst)
        return True

    def copy_for_scene(self, project_id: str, instance_id: str, scene_id: str) -> Instance | None:
        with self._lock:
            inst = self._instances.get(self._make_key(project_id, instance_id, "project"))
            if inst is None:
                return None
            clone = inst.deep_copy()
            clone.scope = f"scene:{scene_id}"
            key = self._make_key(project_id, clone.instance_id, clone.scope)
            if key in self._instances:
                raise ValueError(f"CoW copy {instance_id} for scene {scene_id} already exists")
            self._instances[key] = clone
            try:
                self._register_instance(clone)
            except Exception:
                self._instances.pop(key, None)
                raise
        self._save_to_store(clone)
        return clone
