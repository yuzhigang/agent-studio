import pytest
from src.runtime.instance_manager import InstanceManager
from src.runtime.event_bus import EventBusRegistry
from src.runtime.scene_manager import SceneManager


def test_shared_scene_event_reaches_all_references():
    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    ctrl = SceneManager(im, bus_reg)

    im.create(world_id="world-01", model_name="ladle", instance_id="ladle-001", scope="world")
    im.create(world_id="world-01", model_name="caster", instance_id="caster-03", scope="world")

    ctrl.start(world_id="world-01", scene_id="monitor", mode="shared", references=["ladle-001", "caster-03"])

    bus = bus_reg.get_or_create("world-01")
    received = {"ladle-001": [], "caster-03": []}
    bus.register("ladle-001", "world", "ladleLoaded", lambda t, p, s: received["ladle-001"].append(p))
    bus.register("caster-03", "world", "ladleLoaded", lambda t, p, s: received["caster-03"].append(p))

    bus.publish("ladleLoaded", {"ladleId": "ladle-001"}, source="ladle-001", scope="world")
    assert len(received["ladle-001"]) == 1
    assert len(received["caster-03"]) == 1


def test_isolated_scene_event_does_not_escape():
    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    ctrl = SceneManager(im, bus_reg)

    im.create(world_id="world-01", model_name="ladle", instance_id="ladle-001", scope="world")
    ctrl.start(world_id="world-01", scene_id="drill", mode="isolated", references=["ladle-001"])

    cow = im.get("world-01", "ladle-001", scope="scene:drill")
    assert cow is not None

    bus = bus_reg.get_or_create("world-01")
    world_received = []
    scene_received = []
    bus.register("ladle-001", "world", "ladleLoaded", lambda t, p, s: world_received.append(p))
    bus.register(cow.id, "scene:drill", "ladleLoaded", lambda t, p, s: scene_received.append(p))

    bus.publish("ladleLoaded", {"ladleId": "cow-001"}, source=cow.id, scope="scene:drill")
    assert len(world_received) == 0
    assert len(scene_received) == 1
    assert scene_received[0] == {"ladleId": "cow-001"}


def test_isolated_scene_with_local_instance_and_stop():
    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    ctrl = SceneManager(im, bus_reg)

    im.create(world_id="world-01", model_name="ladle", instance_id="ladle-001", scope="world")
    ctrl.start(
        world_id="world-01",
        scene_id="drill",
        mode="isolated",
        references=["ladle-001"],
        local_instances={"temp-inspector-01": {"modelName": "inspector"}},
    )

    assert im.get("world-01", "temp-inspector-01", scope="scene:drill") is not None

    ctrl.stop("world-01", "drill")

    assert im.list_by_scope("world-01", "scene:drill") == []
    assert im.get("world-01", "ladle-001", scope="world") is not None


def test_linked_reference_auto_pull():
    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    ctrl = SceneManager(im, bus_reg)

    im.create(world_id="world-01", model_name="ladle", instance_id="ladle-001", scope="world", links={"caster": "caster-03"})
    im.create(world_id="world-01", model_name="caster", instance_id="caster-03", scope="world", links={"slab": "slab-08921"})
    im.create(world_id="world-01", model_name="slab", instance_id="slab-08921", scope="world")

    scene = ctrl.start(world_id="world-01", scene_id="monitor", mode="shared", references=["ladle-001"])
    assert set(scene["references"]) == {"ladle-001", "caster-03", "slab-08921"}


class FakeMetricStore:
    def __init__(self, value):
        self._value = value

    def latest(self, world_id, instance_id, variable_name):
        return self._value


def test_metric_backfill_and_reconciliation_do_not_crash():
    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    metric_store = FakeMetricStore(value=42.0)
    ctrl = SceneManager(im, bus_reg, metric_store=metric_store)

    model = {
        "variables": {
            "temperature": {"x-category": "metric"},
        },
    }
    im.create(world_id="world-01", model_name="ladle", instance_id="ladle-001", scope="world", model=model)
    scene = ctrl.start(world_id="world-01", scene_id="drill", mode="isolated", references=["ladle-001"])

    cow = im.get("world-01", "ladle-001", scope="scene:drill")
    assert cow is not None
    assert cow.variables["temperature"] == 42.0
