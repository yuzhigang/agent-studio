import re

from src.runtime.lib.sandbox import SandboxExecutor
from src.runtime.trigger_registry import Trigger

PROPERTY_SECTIONS = {"state", "variables", "attributes", "derivedProperties"}


def _extract_condition_deps(condition_expr):
    """Extract field paths referenced in a condition expression.

    The ConditionTrigger.on_registered hook stores these in entry.watch,
    which the global DependencyIndex uses for O(1) value-change routing.
    """
    matches = re.findall(
        r'this\.([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)',
        condition_expr,
    )
    return list(set(
        m for m in matches
        if m.split(".")[0] in PROPERTY_SECTIONS
    ))


class ConditionTrigger(Trigger):
    trigger_types = {"condition"}

    def __init__(self, sandbox):
        self._sandbox = sandbox or SandboxExecutor()

    def on_registered(self, entry):
        condition_expr = entry.trigger.get("condition", "")
        entry.watch = _extract_condition_deps(condition_expr)

    def handle_value_change(self, entry, instance, field_path, old_val, new_val):
        """Per-entry handler called by TriggerRegistry.notify_value_change.

        Receives a single pre-routed entry (already matched by field_path and instance
        via the global DependencyIndex). Evaluates the condition expression and fires
        the callback if it holds.
        """
        condition_expr = entry.trigger.get("condition", "")
        context = {"this": _build_this_proxy(instance)}
        try:
            result = self._sandbox.evaluate_expression(condition_expr, context)
        except Exception:
            return
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
