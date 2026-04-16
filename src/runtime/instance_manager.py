import threading
import copy
import functools
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Callable

from src.runtime.instance import Instance
from src.runtime.lib.sandbox import SandboxExecutor


class _DictProxy:
    """Wrap a dict so that keys can be accessed as attributes (read/write)."""

    def __init__(self, data: dict):
        object.__setattr__(self, "_data", data)

    def __getattr__(self, name: str):
        try:
            val = self._data[name]
        except KeyError:
            raise AttributeError(name)
        if isinstance(val, dict):
            return _DictProxy(val)
        return val

    def __setattr__(self, name: str, value):
        if name == "_data":
            object.__setattr__(self, name, value)
            return
        self._data[name] = value

    def get(self, key, default=None):
        val = self._data.get(key, default)
        if isinstance(val, dict):
            return _DictProxy(val)
        return val

    def __getitem__(self, key):
        val = self._data[key]
        if isinstance(val, dict):
            return _DictProxy(val)
        return val

    def __setitem__(self, key, value):
        self._data[key] = value


def _wrap_instance(instance: Instance):
    """Expose an Instance as a namespace compatible with behavior scripts."""
    ns = SimpleNamespace()
    ns.id = instance.id
    ns.instance_id = instance.instance_id
    ns.model_name = instance.model_name
    ns.project_id = instance.project_id
    ns.scope = instance.scope
    ns.model_version = instance.model_version
    ns.attributes = _DictProxy(instance.attributes)
    ns.variables = _DictProxy(instance.variables)
    ns.links = _DictProxy(instance.links)
    ns.memory = _DictProxy(instance.memory)
    ns.state = _DictProxy(instance.state)
    ns.audit = _DictProxy(instance.audit)
    ns.lifecycle_state = instance.lifecycle_state
    return ns


class InstanceManager:
    def __init__(
        self,
        event_bus_registry=None,
        instance_store=None,
        model_loader: Callable[[str], dict | None] | None = None,
        sandbox_executor: SandboxExecutor | None = None,
    ):
        self._instances: dict[tuple[str, str], Instance] = {}
        self._lock = threading.Lock()
        self._bus_reg = event_bus_registry
        self._store = instance_store
        self._model_loader = model_loader
        self._sandbox = sandbox_executor or SandboxExecutor()

    @staticmethod
    def _make_key(project_id: str, instance_id: str, scope: str = "project") -> tuple[str, str]:
        if scope.startswith("scene:"):
            scene_id = scope.split(":", 1)[1]
            return (project_id, f"{instance_id}@scene:{scene_id}")
        return (project_id, instance_id)

    def _build_behavior_context(self, instance: Instance, payload: dict, source: str) -> dict:
        bus = None
        if self._bus_reg is not None:
            bus = self._bus_reg.get_or_create(instance.project_id)

        def dispatch(event_type: str, payload_dict: dict, target: str | None = None):
            if bus is not None:
                bus.publish(event_type, payload_dict, source=instance.id, scope=instance.scope, target=target)

        return {
            "this": _wrap_instance(instance),
            "payload": _DictProxy(payload),
            "source": source,
            "dispatch": dispatch,
        }

    def _execute_action(self, instance: Instance, action: dict, payload: dict, source: str) -> None:
        action_type = action.get("type")
        context = self._build_behavior_context(instance, payload, source)

        if action_type == "runScript":
            script = action.get("script", "")
            engine = action.get("scriptEngine", "python")
            if engine == "python" and script:
                try:
                    self._sandbox.execute(script, context)
                except Exception:
                    # Swallow sandbox errors to avoid breaking the event bus
                    pass

        elif action_type == "triggerEvent":
            event_name = action.get("name")
            action_payload = action.get("payload", {})
            evaluated: dict = {}
            for k, v in action_payload.items():
                if isinstance(v, str):
                    try:
                        evaluated[k] = self._sandbox.execute(f"result = {v}", context)
                    except Exception:
                        evaluated[k] = v
                else:
                    evaluated[k] = v
            dispatch_fn = context.get("dispatch")
            if dispatch_fn and event_name:
                dispatch_fn(event_name, evaluated)

    def _on_event(self, instance: Instance, event_type: str, payload: dict, source: str):
        model = instance.model or {}
        behaviors = model.get("behaviors") or {}

        for behavior in behaviors.values():
            trigger = behavior.get("trigger", {})
            if trigger.get("type") != "event":
                continue
            if trigger.get("name") != event_type:
                continue

            when_expr = trigger.get("when")
            if when_expr:
                context = self._build_behavior_context(instance, payload, source)
                expr = when_expr.replace("null", "None") if isinstance(when_expr, str) else when_expr
                try:
                    if not self._sandbox.execute(f"result = ({expr})", context):
                        continue
                except Exception:
                    continue

            for action in behavior.get("actions", []):
                self._execute_action(instance, action, payload, source)

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
