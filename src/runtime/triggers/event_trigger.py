from src.runtime.trigger_registry import Trigger


class EventTrigger(Trigger):
    trigger_types = {"event"}

    def __init__(self, event_bus_registry):
        self._bus_reg = event_bus_registry
        self._handlers = {}  # entry.id -> (world_id, handler_func)

    @staticmethod
    def _inst_attr(inst, name):
        return getattr(inst, name, None) if hasattr(inst, name) else inst.get(name)

    def on_registered(self, entry):
        world_id = self._inst_attr(entry.instance, "world_id")
        scope = self._inst_attr(entry.instance, "scope")
        bus = self._bus_reg.get_or_create(world_id)

        def handler(event_type, payload, source):
            entry.callback(entry.instance, payload=payload, source=source, event_type=event_type)

        self._handlers[entry.id] = (world_id, handler)
        bus.register(self._inst_attr(entry.instance, "id"), scope, entry.trigger["name"], handler)

    def on_unregistered(self, entry):
        info = self._handlers.pop(entry.id, None)
        if info:
            world_id, handler = info
            bus = self._bus_reg.get_or_create(world_id)
            bus.unregister(self._inst_attr(entry.instance, "id"))

    def on_instance_removed(self, instance):
        to_remove = [eid for eid, (wid, h) in self._handlers.items()
                     if wid == self._inst_attr(instance, "world_id")]
        for eid in to_remove:
            info = self._handlers.pop(eid, None)
            if info:
                world_id, handler = info
                bus = self._bus_reg.get_or_create(world_id)
                bus.unregister(self._inst_attr(instance, "id"))
