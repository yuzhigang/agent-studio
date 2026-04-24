# src/runtime/trigger_registry.py
"""Trigger abstraction and global DependencyIndex for O(1) value-change routing."""
import threading
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict


class TriggerEntry:
    def __init__(self, instance, trigger, callback, tag):
        self.id = str(uuid.uuid4())
        self.instance = instance
        self.trigger = trigger
        self.callback = callback
        self.tag = tag
        # Populated by trigger impls during on_registered:
        # list of "section.key" field paths this entry watches.
        self.watch: list[str] = []


class DependencyIndex:
    """Maps field_path → list[TriggerEntry] for O(1) value-change routing.

    Entries are registered by TriggerRegistry after each impl's on_registered
    hook has had a chance to populate entry.watch.
    """

    def __init__(self):
        self._by_field: dict[str, list[TriggerEntry]] = defaultdict(list)

    def register(self, entry):
        for field in entry.watch:
            self._by_field[field].append(entry)

    def unregister(self, entry):
        for field in entry.watch:
            self._by_field[field] = [e for e in self._by_field[field] if e.id != entry.id]

    def get_affected(self, field_path: str, instance) -> list[TriggerEntry]:
        """Return entries watching *field_path* that belong to *instance*."""
        return [e for e in self._by_field.get(field_path, []) if e.instance is instance]


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
        self._triggers: dict[str, Trigger] = {}
        self._registrations: dict[str, TriggerEntry] = {}
        self._dep_index = DependencyIndex()
        self._lock = threading.Lock()

    def add_trigger(self, trigger_impl: Trigger):
        with self._lock:
            for t in trigger_impl.trigger_types:
                self._triggers[t] = trigger_impl

    def register(self, instance, trigger_cfg, callback, tag=None):
        trigger_type = trigger_cfg["type"]
        with self._lock:
            trigger_impl = self._triggers.get(trigger_type)
        if trigger_impl is None:
            raise ValueError(f"Unknown trigger type: {trigger_type}")
        entry = TriggerEntry(instance, trigger_cfg, callback, tag)
        with self._lock:
            self._registrations[entry.id] = entry
        trigger_impl.on_registered(entry)
        self._dep_index.register(entry)
        return entry.id

    def unregister(self, trigger_id):
        with self._lock:
            entry = self._registrations.pop(trigger_id, None)
        if entry:
            self._dep_index.unregister(entry)
            with self._lock:
                trigger_impl = self._triggers.get(entry.trigger["type"])
            if trigger_impl:
                trigger_impl.on_unregistered(entry)

    def unregister_instance(self, instance):
        with self._lock:
            entries = [e for e in self._registrations.values() if e.instance is instance]
        for entry in entries:
            self.unregister(entry.id)
        with self._lock:
            impls = list(self._triggers.values())
        for trigger_impl in impls:
            trigger_impl.on_instance_removed(instance)

    def notify_value_change(self, instance, field_path, old_val, new_val):
        """Route value-change notifications via DependencyIndex — O(1), no impl iteration."""
        entries = self._dep_index.get_affected(field_path, instance)
        for entry in entries:
            trigger_impl = self._triggers.get(entry.trigger["type"])
            if trigger_impl and hasattr(trigger_impl, "handle_value_change"):
                trigger_impl.handle_value_change(entry, instance, field_path, old_val, new_val)
