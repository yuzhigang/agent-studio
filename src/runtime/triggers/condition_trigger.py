import re
from collections import defaultdict

from src.runtime.trigger_registry import Trigger

PROPERTY_SECTIONS = {"state", "variables", "attributes", "derivedProperties"}


def _extract_condition_deps(condition_expr):
    matches = re.findall(
        r'this\.([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)',
        condition_expr,
    )
    return list(set(
        m for m in matches
        if m.split(".")[0] in PROPERTY_SECTIONS
    ))


class ConditionIndex:
    def __init__(self):
        self._by_field = defaultdict(list)

    def register(self, entry):
        for field in getattr(entry, "watch", []):
            self._by_field[field].append(entry)

    def unregister(self, entry):
        for field in getattr(entry, "watch", []):
            self._by_field[field] = [e for e in self._by_field[field] if e.id != entry.id]

    def get_affected(self, changed_fields):
        affected = set()
        for field in changed_fields:
            affected.update(self._by_field.get(field, []))
        return list(affected)


class ConditionTrigger(Trigger):
    trigger_types = {"condition"}

    def __init__(self, sandbox):
        self._sandbox = sandbox
        self._index = ConditionIndex()

    def on_registered(self, entry):
        condition_expr = entry.trigger.get("condition", "")
        entry.watch = _extract_condition_deps(condition_expr)
        self._index.register(entry)

    def on_unregistered(self, entry):
        self._index.unregister(entry)

    def on_instance_removed(self, instance):
        for entry in list(self._index.get_affected(set(self._index._by_field.keys()))):
            if entry.instance is instance:
                self._index.unregister(entry)

    def handle_value_change(self, instance, field_path, old_val, new_val):
        affected = self._index.get_affected({field_path})
        for entry in affected:
            if entry.instance is not instance:
                continue
            condition_expr = entry.trigger.get("condition", "")
            ctx = {"this": _build_this_proxy(instance)}
            try:
                result = eval(condition_expr, {"__builtins__": {}}, ctx)
            except Exception:
                continue
            if result:
                entry.callback(instance)


class _DictProxy:
    def __init__(self, d):
        self._d = d
    def __getattr__(self, name):
        return self._d.get(name)


def _build_this_proxy(instance):
    class ThisProxy:
        pass
    proxy = ThisProxy()
    for section in PROPERTY_SECTIONS:
        if hasattr(instance, section):
            val = getattr(instance, section)
            if isinstance(val, dict):
                setattr(proxy, section, _DictProxy(val))
            else:
                setattr(proxy, section, val)
    return proxy
