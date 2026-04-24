from dataclasses import dataclass

from src.runtime.trigger_registry import Trigger


@dataclass
class _HandlerInfo:
    world_id: str
    instance: object
    callback: object  # event handler function registered with EventBus


class EventTrigger(Trigger):
    trigger_types = {"event"}

    def __init__(self, event_bus_registry):
        self._bus_reg = event_bus_registry
        self._handlers: dict[str, _HandlerInfo] = {}  # entry.id -> handler info

    @staticmethod
    def _inst_attr(inst, name):
        return getattr(inst, name, None) if hasattr(inst, name) else inst.get(name)

    def on_registered(self, entry):
        world_id = self._inst_attr(entry.instance, "world_id")
        scope = self._inst_attr(entry.instance, "scope")
        bus = self._bus_reg.get_or_create(world_id)

        def handler(event_type, payload, source):
            entry.callback(entry.instance, payload=payload, source=source, event_type=event_type)

        self._handlers[entry.id] = _HandlerInfo(
            world_id=world_id, instance=entry.instance, callback=handler,
        )
        bus.register(self._inst_attr(entry.instance, "id"), scope, entry.trigger["name"], handler)

    def on_unregistered(self, entry):
        info = self._handlers.pop(entry.id, None)
        if info:
            bus = self._bus_reg.get_or_create(info.world_id)
            bus.unregister(self._inst_attr(entry.instance, "id"))

    def on_instance_removed(self, instance):
        removed = []
        for eid, info in list(self._handlers.items()):
            if info.instance is instance:
                self._handlers.pop(eid, None)
                removed.append(info)
        # Deduplicate: bus.unregister only once per instance
        seen = set()
        for info in removed:
            key = (info.world_id, self._inst_attr(info.instance, "id"))
            if key not in seen:
                seen.add(key)
                bus = self._bus_reg.get_or_create(info.world_id)
                bus.unregister(self._inst_attr(info.instance, "id"))
