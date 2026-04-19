import pytest
from src.runtime.trigger_registry import TriggerRegistry, TriggerEntry


class FakeTrigger:
    trigger_types = {"fake"}
    def __init__(self):
        self.registered = []
        self.unregistered = []
        self.removed_instances = []

    def on_registered(self, entry):
        self.registered.append(entry)

    def on_unregistered(self, entry):
        self.unregistered.append(entry)

    def on_instance_removed(self, instance):
        self.removed_instances.append(instance)


def test_register_and_unregister():
    reg = TriggerRegistry()
    fake = FakeTrigger()
    reg.add_trigger(fake)

    inst = object()
    trigger_cfg = {"type": "fake", "name": "test"}
    callback = lambda i: None

    tid = reg.register(inst, trigger_cfg, callback, tag="b1")
    assert tid is not None
    assert len(fake.registered) == 1
    assert fake.registered[0].instance is inst
    assert fake.registered[0].trigger == trigger_cfg
    assert fake.registered[0].callback is callback
    assert fake.registered[0].tag == "b1"

    reg.unregister(tid)
    assert len(fake.unregistered) == 1


def test_unregister_instance():
    reg = TriggerRegistry()
    fake = FakeTrigger()
    reg.add_trigger(fake)

    inst1 = object()
    inst2 = object()
    reg.register(inst1, {"type": "fake", "name": "a"}, lambda i: None, tag="b1")
    reg.register(inst1, {"type": "fake", "name": "b"}, lambda i: None, tag="b2")
    reg.register(inst2, {"type": "fake", "name": "c"}, lambda i: None, tag="b3")

    reg.unregister_instance(inst1)
    assert len(fake.unregistered) == 2
    assert len(fake.removed_instances) == 1
    assert fake.removed_instances[0] is inst1


def test_unknown_trigger_type_raises():
    reg = TriggerRegistry()
    with pytest.raises(ValueError, match="Unknown trigger type"):
        reg.register(object(), {"type": "nonexistent"}, lambda i: None)


def test_trigger_entry_has_unique_id():
    inst = object()
    e1 = TriggerEntry(inst, {"type": "event", "name": "x"}, lambda i: None, "b1")
    e2 = TriggerEntry(inst, {"type": "event", "name": "x"}, lambda i: None, "b1")
    assert e1.id != e2.id
