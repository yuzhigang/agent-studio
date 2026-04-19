# src/runtime/trigger_registry.py
import uuid
from abc import ABC, abstractmethod


class TriggerEntry:
    def __init__(self, instance, trigger, callback, tag):
        self.id = str(uuid.uuid4())
        self.instance = instance
        self.trigger = trigger
        self.callback = callback
        self.tag = tag


class Trigger(ABC):
    @property
    @abstractmethod
    def trigger_types(self):
        """Return set of trigger type strings this implementation handles."""
        pass

    def on_registered(self, entry):
        pass

    def on_unregistered(self, entry):
        pass

    def on_instance_removed(self, instance):
        pass


class TriggerRegistry:
    def __init__(self):
        self._triggers = {}          # type -> Trigger implementation
        self._registrations = {}     # trigger_id -> TriggerEntry

    def add_trigger(self, trigger_impl):
        for t in trigger_impl.trigger_types:
            self._triggers[t] = trigger_impl

    def register(self, instance, trigger_cfg, callback, tag=None):
        trigger_impl = self._triggers.get(trigger_cfg["type"])
        if trigger_impl is None:
            raise ValueError(f"Unknown trigger type: {trigger_cfg['type']}")
        entry = TriggerEntry(instance, trigger_cfg, callback, tag)
        self._registrations[entry.id] = entry
        trigger_impl.on_registered(entry)
        return entry.id

    def unregister(self, trigger_id):
        entry = self._registrations.pop(trigger_id, None)
        if entry:
            trigger_impl = self._triggers.get(entry.trigger["type"])
            if trigger_impl:
                trigger_impl.on_unregistered(entry)

    def unregister_instance(self, instance):
        for entry in list(self._registrations.values()):
            if entry.instance is instance:
                self.unregister(entry.id)
        for trigger_impl in self._triggers.values():
            trigger_impl.on_instance_removed(instance)

    def notify_value_change(self, instance, field_path, old_val, new_val):
        for trigger_impl in self._triggers.values():
            if hasattr(trigger_impl, "handle_value_change"):
                trigger_impl.handle_value_change(instance, field_path, old_val, new_val)
