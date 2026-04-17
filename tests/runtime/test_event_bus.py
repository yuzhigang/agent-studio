import pytest
from src.runtime.event_bus import EventBus

def test_pre_publish_hook_called_on_publish():
    bus = EventBus()
    calls = []
    def hook(event_type, payload, source, scope, target):
        calls.append((event_type, payload, source, scope, target))
    bus.add_pre_publish_hook(hook)
    bus.publish("test.event", {"a": 1}, "src-1", "project", "tgt-1")
    assert len(calls) == 1
    assert calls[0] == ("test.event", {"a": 1}, "src-1", "project", "tgt-1")

def test_remove_pre_publish_hook():
    bus = EventBus()
    calls = []
    received = []
    def hook(event_type, payload, source, scope, target):
        calls.append(event_type)
    def handler(event_type, payload, source):
        received.append((event_type, payload, source))
    bus.add_pre_publish_hook(hook)
    bus.remove_pre_publish_hook(hook)
    bus.register("inst-1", "project", "test.event", handler)
    bus.publish("test.event", {}, "src-1", "project")
    assert len(calls) == 0
    assert len(received) == 1
    assert received[0] == ("test.event", {}, "src-1")

def test_publish_delivers_to_subscriber():
    bus = EventBus()
    received = []
    def handler(event_type, payload, source):
        received.append((event_type, payload, source))
    bus.register("ladle-001", "project", "ladleLoaded", handler)
    bus.publish("ladleLoaded", {"steelAmount": 180}, "caster-03", "project")
    assert len(received) == 1
    assert received[0] == ("ladleLoaded", {"steelAmount": 180}, "caster-03")

def test_scope_isolation_scene_vs_project():
    bus = EventBus()
    scene_received = []
    proj_received = []
    bus.register("ladle-001", "scene:drill", "ladleLoaded", lambda t, p, s: scene_received.append(t))
    bus.register("ladle-002", "project", "ladleLoaded", lambda t, p, s: proj_received.append(t))
    bus.publish("ladleLoaded", {}, "caster-03", "scene:drill")
    assert len(scene_received) == 1
    assert len(proj_received) == 0

from src.runtime.event_bus import EventBusRegistry

def test_registry_get_or_create_and_destroy():
    registry = EventBusRegistry()
    bus1 = registry.get_or_create("proj-a")
    bus2 = registry.get_or_create("proj-a")
    assert bus1 is bus2
    bus3 = registry.get_or_create("proj-b")
    assert bus3 is not bus1
    registry.destroy("proj-a")
    bus4 = registry.get_or_create("proj-a")
    assert bus4 is not bus1
