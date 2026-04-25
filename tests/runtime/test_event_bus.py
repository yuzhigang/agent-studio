import pytest

from src.runtime.event_bus import EventBus, EventBusRegistry


def test_event_bus_publish_does_not_require_message_hub_hook():
    bus = EventBus()
    seen = []
    bus.register("inst-1", "world", "local.event", lambda t, p, s: seen.append((t, p, s)))

    bus.publish("local.event", {"ok": True}, "tester", "world")

    assert seen == [("local.event", {"ok": True}, "tester")]


def test_event_bus_target_routes_to_single_instance():
    bus = EventBus()
    target_hits = []
    other_hits = []
    bus.register("inst-target", "world", "notify.alert", lambda t, p, s: target_hits.append(s))
    bus.register("inst-other", "world", "notify.alert", lambda t, p, s: other_hits.append(s))

    bus.publish("notify.alert", {"level": "high"}, "ext-1", "world", target="inst-target")

    assert target_hits == ["ext-1"]
    assert other_hits == []


def test_event_bus_scene_scope_is_isolated_from_other_scopes():
    bus = EventBus()
    scene_hits = []
    other_scene_hits = []
    world_hits = []
    bus.register("scene-a", "scene:drill", "ladleLoaded", lambda t, p, s: scene_hits.append(t))
    bus.register("scene-b", "scene:pour", "ladleLoaded", lambda t, p, s: other_scene_hits.append(t))
    bus.register("world-a", "world", "ladleLoaded", lambda t, p, s: world_hits.append(t))

    bus.publish("ladleLoaded", {}, "caster-03", "scene:drill")

    assert scene_hits == ["ladleLoaded"]
    assert other_scene_hits == []
    assert world_hits == []


def test_registry_get_or_create_and_destroy():
    registry = EventBusRegistry()
    bus1 = registry.get_or_create("world-a")
    bus2 = registry.get_or_create("world-a")
    assert bus1 is bus2

    registry.destroy("world-a")

    bus3 = registry.get_or_create("world-a")
    assert bus3 is not bus1


def test_handler_failure_does_not_interrupt_other_subscribers():
    bus = EventBus()
    hits = []

    def buggy_handler(event_type, payload, source):
        raise RuntimeError("boom")

    def good_handler(event_type, payload, source):
        hits.append((event_type, source))

    bus.register("inst-buggy", "world", "test.event", buggy_handler)
    bus.register("inst-good", "world", "test.event", good_handler)

    bus.publish("test.event", {}, "src-1", "world")

    assert hits == [("test.event", "src-1")]


def test_publish_raise_on_error_propagates_handler_failure():
    bus = EventBus()

    def buggy_handler(event_type, payload, source):
        raise RuntimeError("boom")

    bus.register("inst-buggy", "world", "test.event", buggy_handler)

    with pytest.raises(RuntimeError, match="boom"):
        bus.publish("test.event", {}, "src-1", "world", raise_on_error=True)
