import logging
import os
from pathlib import Path

import yaml

from src.runtime.agent_namespace import agent_namespace_for_path
from src.runtime.instance_loader import InstanceLoader
from src.runtime.lib.registry import LibRegistry
from src.runtime.lib.sandbox import SandboxExecutor
from src.runtime.locks.world_lock import WorldLock
from src.runtime.messaging import WorldMessageIngress, WorldMessageSender
from src.runtime.model_loader import ModelLoader
from src.runtime.model_resolver import ModelResolver
from src.runtime.stores.sqlite_store import SQLiteStore
from src.runtime.event_bus import EventBusRegistry
from src.runtime.instance_manager import InstanceManager
from src.runtime.scene_manager import SceneManager
from src.runtime.state_manager import StateManager
from src.runtime.world_state import WorldState
from src.runtime.trigger_registry import TriggerRegistry
from src.runtime.alarm_manager import AlarmManager
from src.runtime.triggers.event_trigger import EventTrigger
from src.runtime.triggers.condition_trigger import ConditionTrigger
from src.runtime.triggers.timer_trigger import TimerTrigger
from src.runtime.world_event_emitter import WorldEventEmitter

logger = logging.getLogger(__name__)


class WorldRegistry:
    def __init__(
        self,
        base_dir: str = "worlds",
        global_model_paths=None,
        metric_store_factory=None,
    ):
        self._base_dir = base_dir
        self._global_model_paths = global_model_paths or []
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
            world_state = WorldState(None, world_id)

            resolver = ModelResolver(world_dir, self._global_model_paths)
            world_agents_dir = Path(world_dir) / "agents"

            def model_loader(model_id: str) -> dict | None:
                model_dir = resolver.resolve(model_id)
                if model_dir is not None:
                    return ModelLoader.load(model_dir.parent)
                return None

            def agent_namespace_resolver(model_id: str) -> str | None:
                model_dir = resolver.resolve(model_id)
                if model_dir is None:
                    return None
                scan_roots = [world_agents_dir, *[Path(p) for p in self._global_model_paths]]
                for root in scan_roots:
                    namespace = agent_namespace_for_path(model_dir, root, "model")
                    if namespace is not None:
                        return namespace
                return None

            trigger_registry = TriggerRegistry()
            trigger_registry.add_trigger(EventTrigger(bus_reg))
            trigger_registry.add_trigger(TimerTrigger())

            bus = bus_reg.get_or_create(world_id)
            lib_registry = LibRegistry()
            global_roots = [Path(path) for path in self._global_model_paths]
            first_scan = True
            for root in [*global_roots, world_agents_dir]:
                if not root.exists():
                    continue
                lib_registry.scan(str(root), clear=first_scan)
                first_scan = False
            sandbox_executor = SandboxExecutor(registry=lib_registry)

            im = InstanceManager(
                bus_reg,
                instance_store=store,
                model_loader=model_loader,
                agent_namespace_resolver=agent_namespace_resolver,
                sandbox_executor=sandbox_executor,
                world_state=world_state,
                world_event_emitter=None,
                trigger_registry=trigger_registry,
                alarm_manager=None,
            )

            trigger_registry.add_trigger(ConditionTrigger(im._sandbox))

            world_state.set_instance_manager(im)
            message_sender = WorldMessageSender(
                world_id=world_id,
                hub=None,
                source=f"world:{world_id}",
            )
            event_emitter = WorldEventEmitter(bus, im, message_sender)
            im.bind_world_event_emitter(event_emitter)
            alarm_manager = AlarmManager(trigger_registry, event_emitter, store)
            im.bind_alarm_manager(alarm_manager)
            message_receiver = WorldMessageIngress(event_emitter)

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
                world_event_emitter=event_emitter,
            )
            scene_mgr.set_state_manager(state_mgr)

            self._load_instance_declarations(world_id, world_dir, im, model_loader)

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
                "world_state": world_state,
                "lib_registry": lib_registry,
                "lock": world_lock,
                "alarm_manager": alarm_manager,
                "_registry": self,
                "force_stop_on_shutdown": False,
                "runtime_status": "running",
                "event_emitter": event_emitter,
                "message_receiver": message_receiver,
                "message_sender": message_sender,
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

    @staticmethod
    def _merge_defaults(model_specs: dict, overrides: dict) -> dict:
        result = {}
        for key, spec in model_specs.items():
            if isinstance(spec, dict):
                result[key] = overrides.get(key, spec.get("default"))
            else:
                result[key] = overrides.get(key, spec)
        for key, value in overrides.items():
            if key not in result:
                result[key] = value
        return result

    def _load_instance_declarations(
        self,
        world_id: str,
        world_dir: str,
        im: InstanceManager,
        model_loader,
    ) -> None:
        """Scan and create static instances from *.instance.yaml declarations."""
        declarations = InstanceLoader.scan(world_dir)
        for decl in declarations:
            model_id = decl.get("modelId")
            instance_id = decl.get("id")
            if not model_id or not instance_id:
                logger.warning(
                    "Skipping instance declaration missing modelId or id: %s",
                    decl.get("_source_file", "unknown"),
                )
                continue

            model = model_loader(model_id)
            if model is None:
                logger.warning(
                    "Skipping instance declaration %s: model %s not found",
                    instance_id,
                    model_id,
                )
                continue

            # Merge defaults with overrides
            variables = self._merge_defaults(
                model.get("variables") or {}, decl.get("variables") or {}
            )
            attributes = self._merge_defaults(
                model.get("attributes") or {}, decl.get("attributes") or {}
            )
            links = self._merge_defaults(
                model.get("links") or {}, decl.get("links") or {}
            )
            memory = self._merge_defaults(
                model.get("memory") or {}, decl.get("memory") or {}
            )

            state = {"current": None, "enteredAt": None}
            if decl.get("state"):
                state["current"] = decl["state"]

            # If instance already exists (from DB or previous declaration), remove it
            # so that declaration wins.
            if im.get(world_id, instance_id, scope="world") is not None:
                im.remove(world_id, instance_id, scope="world")

            im.create(
                world_id=world_id,
                model_name=model_id,
                instance_id=instance_id,
                scope="world",
                agent_namespace=decl.get("_agent_namespace"),
                model=model,
                state=state,
                attributes=attributes,
                variables=variables,
                links=links,
                memory=memory,
            )
