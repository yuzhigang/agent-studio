import threading
import copy
import functools
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Callable

from src.runtime.instance import Instance
from src.runtime.lib.proxy import LibProxy
from src.runtime.lib.sandbox import SandboxExecutor


class _DictProxy:
    """Wrap a dict so that keys can be accessed as attributes (read/write).
    Optionally tracks changed field paths for trigger notification."""

    def __init__(self, data: dict, path_prefix: str = "", changed_fields: list | None = None):
        object.__setattr__(self, "_data", data)
        object.__setattr__(self, "_path_prefix", path_prefix)
        object.__setattr__(self, "_changed_fields", changed_fields)

    def __getattribute__(self, name: str):
        if name in ("_data", "_path_prefix", "_changed_fields", "__class__"):
            return object.__getattribute__(self, name)
        data = object.__getattribute__(self, "_data")
        if name in data:
            val = data[name]
            if isinstance(val, dict):
                path_prefix = object.__getattribute__(self, "_path_prefix")
                changed_fields = object.__getattribute__(self, "_changed_fields")
                nested_prefix = f"{path_prefix}.{name}" if path_prefix else name
                return _DictProxy(val, path_prefix=nested_prefix, changed_fields=changed_fields)
            return val
        return object.__getattribute__(self, name)

    def __setattr__(self, name: str, value):
        if name in ("_data", "_path_prefix", "_changed_fields"):
            object.__setattr__(self, name, value)
            return
        self._data[name] = value
        if self._changed_fields is not None:
            field_path = f"{self._path_prefix}.{name}" if self._path_prefix else name
            self._changed_fields.append(field_path)

    def get(self, key, default=None):
        val = self._data.get(key, default)
        if isinstance(val, dict):
            nested_prefix = f"{self._path_prefix}.{key}" if self._path_prefix else key
            return _DictProxy(val, path_prefix=nested_prefix, changed_fields=self._changed_fields)
        return val

    def __getitem__(self, key):
        val = self._data[key]
        if isinstance(val, dict):
            nested_prefix = f"{self._path_prefix}.{key}" if self._path_prefix else key
            return _DictProxy(val, path_prefix=nested_prefix, changed_fields=self._changed_fields)
        return val

    def __setitem__(self, key, value):
        self._data[key] = value
        if self._changed_fields is not None:
            field_path = f"{self._path_prefix}.{key}" if self._path_prefix else key
            self._changed_fields.append(field_path)

    def __contains__(self, key):
        return key in self._data

    def __iter__(self):
        return iter(self._data)

    def items(self):
        return self._data.items()

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()


def _wrap_instance(instance: Instance, changed_fields: list | None = None):
    """Expose an Instance as a namespace compatible with behavior scripts."""
    ns = SimpleNamespace()
    ns.id = instance.id
    ns.instance_id = instance.instance_id
    ns.model_name = instance.model_name
    ns.world_id = instance.world_id
    ns.scope = instance.scope
    ns.model_version = instance.model_version
    ns.attributes = _DictProxy(instance.attributes, path_prefix="attributes", changed_fields=changed_fields)
    ns.variables = _DictProxy(instance.variables, path_prefix="variables", changed_fields=changed_fields)
    ns.bindings = _DictProxy(instance.bindings)
    ns.links = _DictProxy(instance.links)
    ns.memory = _DictProxy(instance.memory)
    ns.state = _DictProxy(instance.state, path_prefix="state", changed_fields=changed_fields)
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
        world_state=None,
        world_event_emitter=None,
        trigger_registry=None,
        alarm_manager=None,
    ):
        self._instances: dict[tuple[str, str], Instance] = {}
        self._lock = threading.Lock()
        self._bus_reg = event_bus_registry
        self._store = instance_store
        self._model_loader = model_loader
        self._sandbox = sandbox_executor or SandboxExecutor()
        self._world_state = world_state
        self._event_emitter = world_event_emitter
        self._trigger_registry = trigger_registry
        self._alarm_manager = alarm_manager

    def bind_world_event_emitter(self, world_event_emitter) -> None:
        self._event_emitter = world_event_emitter

    def bind_alarm_manager(self, alarm_manager) -> None:
        self._alarm_manager = alarm_manager

    @staticmethod
    def _make_key(world_id: str, instance_id: str, scope: str = "world") -> tuple[str, str]:
        if scope.startswith("scene:"):
            scene_id = scope.split(":", 1)[1]
            return (world_id, f"{instance_id}@scene:{scene_id}")
        return (world_id, instance_id)

    def _build_behavior_context(self, instance: Instance, payload: dict, source: str, changed_fields: list | None = None) -> dict:
        bus = None
        if self._bus_reg is not None:
            bus = self._bus_reg.get_or_create(instance.world_id)

        def dispatch(event_type: str, payload_dict: dict, target: str | None = None):
            if self._event_emitter is not None:
                self._event_emitter.publish_from_instance(
                    world_id=instance.world_id,
                    source_instance_id=instance.id,
                    scope=instance.scope,
                    event_type=event_type,
                    payload=payload_dict,
                    target=target,
                )
            elif bus is not None:
                bus.publish(
                    event_type,
                    payload_dict,
                    source=instance.id,
                    scope=instance.scope,
                    target=target,
                )

        world_state = {}
        if self._world_state is not None:
            world_state = self._world_state.snapshot()

        wrapped = _wrap_instance(instance, changed_fields=changed_fields)
        lib_context = {
            "this": wrapped,
            "payload": _DictProxy(payload),
            "source": source,
            "dispatch": dispatch,
            "world_state": _DictProxy(world_state),
        }
        lib_proxy = LibProxy(default_namespace=instance.model_name, lib_context=lib_context)

        return {
            "this": wrapped,
            "payload": _DictProxy(payload),
            "source": source,
            "dispatch": dispatch,
            "world_state": _DictProxy(world_state),
            "lib": lib_proxy,
        }

    def _transition_state(self, instance: Instance, transition_name: str) -> None:
        model = instance.model or {}
        transitions = model.get("transitions") or {}
        tx = transitions.get(transition_name)
        if tx is None:
            raise ValueError(f"Transition '{transition_name}' not found")
        current = instance.state.get("current")
        if tx.get("from") != current:
            # Silent skip: multiple triggers may compete, invalid from is normal
            return
        instance.state["current"] = tx["to"]
        instance.state["enteredAt"] = datetime.now(timezone.utc).isoformat()
        instance._update_snapshot()
        self._save_to_store(instance)
        if self._trigger_registry is not None:
            self._trigger_registry.notify_value_change(instance, "state.current", current, tx["to"])

    def _execute_action(self, instance: Instance, action: dict, payload: dict, source: str, context_override=None) -> None:
        action_type = action.get("type")
        context = context_override or self._build_behavior_context(instance, payload, source)

        if action_type == "transition":
            transition_name = action.get("transition")
            if transition_name:
                self._transition_state(instance, transition_name)

        elif action_type == "runScript":
            script = action.get("script", "")
            engine = action.get("scriptEngine", "python")
            if engine == "python" and script:
                try:
                    self._sandbox.execute(script, context)
                except Exception:
                    # Swallow sandbox errors to avoid breaking the event bus
                    pass
            instance._update_snapshot()

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
            if action.get("external") is True:
                if self._event_emitter is None:
                    raise RuntimeError("External triggerEvent requires a configured WorldEventEmitter")
                target_world_id = action.get("targetWorldId")
                if not target_world_id:
                    raise ValueError("External triggerEvent requires targetWorldId")
                if isinstance(target_world_id, str):
                    try:
                        target_world_id = self._sandbox.execute(f"result = {target_world_id}", context)
                    except Exception:
                        pass
                self._event_emitter.publish_external(
                    target_world_id=target_world_id,
                    event_type=event_name,
                    payload=evaluated,
                    scope=action.get("scope", instance.scope),
                    target=action.get("target"),
                    trace_id=action.get("traceId"),
                    headers=action.get("headers"),
                )
            else:
                dispatch_fn = context.get("dispatch")
                if dispatch_fn and event_name:
                    dispatch_fn(event_name, evaluated)

    def _execute_actions(self, instance: Instance, actions: list, payload: dict, source: str) -> None:
        changed_fields = []
        for action in actions:
            context = self._build_behavior_context(instance, payload, source, changed_fields=changed_fields)
            self._execute_action(instance, action, payload, source, context_override=context)

        if self._trigger_registry is not None:
            for field_path in set(changed_fields):
                parts = field_path.split(".")
                if len(parts) >= 2:
                    section = parts[0]
                    key = parts[1]
                    source_dict = getattr(instance, section, {})
                    new_val = source_dict.get(key)
                    self._trigger_registry.notify_value_change(instance, field_path, None, new_val)

    def _make_behavior_callback(self, instance, trigger, actions):
        def callback(inst, payload=None, source="trigger", **kwargs):
            when_expr = trigger.get("when")
            if when_expr:
                context = self._build_behavior_context(inst, payload or {}, source)
                expr = when_expr.replace("null", "None") if isinstance(when_expr, str) else when_expr
                try:
                    if not self._sandbox.execute(f"result = ({expr})", context):
                        return
                except Exception:
                    return
            self._execute_actions(inst, actions, payload or {}, source)
        return callback

    def _register_instance(self, inst: Instance):
        if self._trigger_registry is None:
            return
        model = inst.model or {}
        behaviors = model.get("behaviors") or {}
        for name, behavior in behaviors.items():
            trigger = behavior.get("trigger")
            if not trigger:
                continue
            actions = behavior.get("actions", [])
            callback = self._make_behavior_callback(inst, trigger, actions)
            self._trigger_registry.register(inst, trigger, callback, tag=name)

    def _unregister_instance(self, inst: Instance):
        if self._bus_reg is not None:
            bus = self._bus_reg.get_or_create(inst.world_id)
            bus.unregister(inst.id)
        if self._trigger_registry is not None:
            self._trigger_registry.unregister_instance(inst)

    def build_persist_dict(self, inst: Instance) -> dict:
        return {
            "model_name": inst.model_name,
            "model_version": inst.model_version,
            "attributes": inst.attributes or {},
            "state": inst.state or {"current": None, "enteredAt": None},
            "variables": inst.variables or {},
            "bindings": inst.bindings or {},
            "links": inst.links or {},
            "memory": inst.memory or {},
            "audit": inst.audit or {"version": 0, "updatedAt": None, "lastEventId": None},
            "lifecycle_state": inst.lifecycle_state,
            "world_state": inst.world_state or {},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _save_to_store(self, inst: Instance):
        if self._store is not None:
            self._store.save_instance(
                inst.world_id, inst.instance_id, inst.scope, self.build_persist_dict(inst)
            )

    def create(
        self,
        world_id: str,
        model_name: str,
        instance_id: str,
        scope: str = "world",
        model_version: str | None = None,
        attributes: dict | None = None,
        variables: dict | None = None,
        bindings: dict | None = None,
        links: dict | None = None,
        memory: dict | None = None,
        state: dict | None = None,
        model: dict | None = None,
    ) -> Instance:
        attributes = attributes or {}
        variables = variables or {}
        bindings = bindings or {}
        links = links or {}
        memory = memory or {}
        state = state or {"current": None, "enteredAt": None}
        inst = Instance(
            instance_id=instance_id,
            model_name=model_name,
            world_id=world_id,
            scope=scope,
            model_version=model_version,
            attributes=copy.deepcopy(attributes),
            variables=copy.deepcopy(variables),
            bindings=copy.deepcopy(bindings),
            links=copy.deepcopy(links),
            memory=copy.deepcopy(memory),
            state=copy.deepcopy(state),
            model=copy.deepcopy(model) if model is not None else None,
        )
        key = self._make_key(world_id, instance_id, scope)
        with self._lock:
            if key in self._instances:
                raise ValueError(f"Instance {instance_id} already exists in world {world_id} with scope {scope}")
            self._instances[key] = inst
            try:
                self._register_instance(inst)
            except Exception:
                self._instances.pop(key, None)
                raise
        inst._update_snapshot()
        self._save_to_store(inst)
        if self._alarm_manager is not None and inst.model:
            alarm_configs = inst.model.get("alarms")
            if alarm_configs:
                self._alarm_manager.register_instance_alarms(inst, alarm_configs)
        return inst

    def get(self, world_id: str, instance_id: str, scope: str = "world") -> Instance | None:
        key = self._make_key(world_id, instance_id, scope)

        # Fast path: already in memory (lock-free check — ok because
        # _instances is a plain dict and only our own logic mutates it)
        inst = self._instances.get(key)
        if inst is not None:
            return inst

        if self._store is None:
            return None

        # Slow path: load from store (I/O — do NOT hold lock during this)
        snapshot = self._store.load_instance(world_id, instance_id, scope)
        if snapshot is None:
            return None

        inst = Instance(
            instance_id=snapshot["instance_id"],
            model_name=snapshot["model_name"],
            world_id=snapshot["world_id"],
            scope=snapshot["scope"],
            model_version=snapshot.get("model_version"),
            attributes=copy.deepcopy(snapshot.get("attributes", {})),
            variables=copy.deepcopy(snapshot.get("variables", {})),
            bindings=copy.deepcopy(snapshot.get("bindings", {})),
            links=copy.deepcopy(snapshot.get("links", {})),
            memory=copy.deepcopy(snapshot.get("memory", {})),
            state=copy.deepcopy(snapshot.get("state", {"current": None, "enteredAt": None})),
            audit=copy.deepcopy(snapshot.get("audit", {"version": 0, "updatedAt": None, "lastEventId": None})),
            lifecycle_state=snapshot.get("lifecycle_state", "active"),
        )
        inst.snapshot = copy.deepcopy(snapshot.get("world_state", {}).get("snapshot", {}))
        if self._model_loader is not None:
            loaded_model = self._model_loader(inst.model_name)
            if loaded_model is not None:
                inst.model = loaded_model
        inst._update_snapshot()

        # Register under lock (fast path — dict ops only)
        with self._lock:
            existing = self._instances.get(key)
            if existing is not None:
                return existing  # another caller loaded it first
            self._instances[key] = inst
            try:
                self._register_instance(inst)
            except Exception:
                self._instances.pop(key, None)
                raise

        # Alarm registration outside lock
        if self._alarm_manager is not None and inst.model:
            alarm_configs = inst.model.get("alarms")
            if alarm_configs:
                self._alarm_manager.register_instance_alarms(inst, alarm_configs)
        return inst

    def list_by_world(self, world_id: str) -> list[Instance]:
        with self._lock:
            return [inst for (pid, _), inst in self._instances.items() if pid == world_id]

    def list_by_scope(self, world_id: str, scope: str) -> list[Instance]:
        with self._lock:
            return [
                inst for (pid, _), inst in self._instances.items()
                if pid == world_id and inst.scope == scope
            ]

    def remove(self, world_id: str, instance_id: str, scope: str = "world") -> bool:
        key = self._make_key(world_id, instance_id, scope)
        with self._lock:
            inst = self._instances.pop(key, None)
        if inst is not None and self._alarm_manager is not None:
            self._alarm_manager.unregister_instance_alarms(inst)
        if inst is not None:
            self._unregister_instance(inst)
            if self._store is not None:
                self._store.delete_instance(world_id, instance_id, scope)
            return True
        return False

    def transition_lifecycle(self, world_id: str, instance_id: str, new_state: str, scope: str = "world") -> bool:
        inst = self.get(world_id, instance_id, scope)
        if inst is None:
            return False
        inst.lifecycle_state = new_state
        inst._update_snapshot()
        self._save_to_store(inst)
        if self._alarm_manager is not None:
            self._alarm_manager.unregister_instance_alarms(inst)
        if new_state == "archived":
            with self._lock:
                self._instances.pop(self._make_key(world_id, instance_id, scope), None)
            self._unregister_instance(inst)
            inst.snapshot = {}
            inst._audit_fields = {}
        return True

    def copy_for_scene(self, world_id: str, instance_id: str, scene_id: str) -> Instance | None:
        with self._lock:
            inst = self._instances.get(self._make_key(world_id, instance_id, "world"))
            if inst is None:
                return None
            clone = inst.deep_copy()
            clone.scope = f"scene:{scene_id}"
            clone._update_snapshot()
            key = self._make_key(world_id, clone.instance_id, clone.scope)
            if key in self._instances:
                raise ValueError(f"CoW copy {instance_id} for scene {scene_id} already exists")
            self._instances[key] = clone
            try:
                self._register_instance(clone)
            except Exception:
                self._instances.pop(key, None)
                raise
        if self._alarm_manager is not None and clone.model:
            alarm_configs = clone.model.get("alarms")
            if alarm_configs:
                self._alarm_manager.register_instance_alarms(clone, alarm_configs)
        self._save_to_store(clone)
        return clone
