# src/runtime/triggers/value_changed_trigger.py
from src.runtime.trigger_registry import Trigger


class ValueChangedTrigger(Trigger):
    trigger_types = {"valueChanged"}

    def __init__(self):
        self._entries = []  # list of TriggerEntry

    def on_registered(self, entry):
        self._entries.append(entry)

    def on_unregistered(self, entry):
        self._entries = [e for e in self._entries if e.id != entry.id]

    def on_instance_removed(self, instance):
        self._entries = [e for e in self._entries if e.instance is not instance]

    def handle_value_change(self, instance, field_path, old_val, new_val):
        for entry in self._entries:
            if entry.instance is not instance:
                continue
            if entry.trigger.get("name") != field_path:
                continue
            target_value = entry.trigger.get("value")
            if target_value is not None and new_val != target_value:
                continue
            entry.callback(instance)
