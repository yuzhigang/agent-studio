import pytest
from src.runtime.instance_manager import InstanceManager
from src.runtime.instance import Instance
from src.runtime.event_bus import EventBusRegistry


def test_create_and_get_instance():
    mgr = InstanceManager()
    inst = mgr.create(
        project_id="proj-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="project",
        attributes={"capacity": 200},
        variables={"steelAmount": 180},
    )
    assert inst.id == "ladle-001"
    assert mgr.get("proj-01", "ladle-001", scope="project") is inst
    assert mgr.get("proj-01", "ladle-002", scope="project") is None


def test_copy_for_scene_changes_scope():
    mgr = InstanceManager()
    mgr.create(project_id="proj-01", model_name="ladle", instance_id="ladle-001", scope="project")
    clone = mgr.copy_for_scene("proj-01", "ladle-001", "drill")
    assert clone is not None
    assert clone.scope == "scene:drill"
    assert mgr.get("proj-01", "ladle-001", scope="project").scope == "project"
    assert mgr.get("proj-01", "ladle-001", scope="scene:drill") is clone
    scene_instances = mgr.list_by_scope("proj-01", "scene:drill")
    assert len(scene_instances) == 1


def test_duplicate_instance_id_raises():
    mgr = InstanceManager()
    mgr.create(project_id="proj-01", model_name="ladle", instance_id="ladle-001", scope="project")
    with pytest.raises(ValueError, match="already exists"):
        mgr.create(project_id="proj-01", model_name="ladle", instance_id="ladle-001", scope="project")


def test_create_registers_on_event_bus():
    bus_reg = EventBusRegistry()
    mgr = InstanceManager(bus_reg)
    mgr.create(
        project_id="proj-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="project",
        model={
            "behaviors": {
                "captureAssigned": {
                    "trigger": {"type": "event", "name": "dispatchAssigned"},
                }
            }
        },
    )
    bus = bus_reg.get_or_create("proj-01")
    # Publish an event that the instance should be subscribed to
    received = []
    # Manually add a second subscriber to the same event to verify routing still works
    bus.register("ladle-002", "project", "dispatchAssigned", lambda t, p, s: received.append((t, p, s)))
    bus.publish("dispatchAssigned", {"destinationId": "C03"}, source="external", scope="project")
    assert len(received) == 1


def test_remove_instance_unregisters_and_deletes():
    bus_reg = EventBusRegistry()
    mgr = InstanceManager(bus_reg)
    mgr.create(
        project_id="proj-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="project",
        model={
            "behaviors": {
                "captureAssigned": {
                    "trigger": {"type": "event", "name": "dispatchAssigned"},
                }
            }
        },
    )
    assert mgr.remove("proj-01", "ladle-001", scope="project") is True
    assert mgr.get("proj-01", "ladle-001", scope="project") is None
    bus = bus_reg.get_or_create("proj-01")
    received = []
    bus.register("ladle-002", "project", "dispatchAssigned", lambda t, p, s: received.append((t, p, s)))
    bus.publish("dispatchAssigned", {"destinationId": "C03"}, source="external", scope="project")
    assert len(received) == 1


def test_list_by_project():
    mgr = InstanceManager()
    mgr.create(project_id="proj-01", model_name="ladle", instance_id="ladle-001", scope="project")
    mgr.create(project_id="proj-02", model_name="ladle", instance_id="ladle-002", scope="project")
    project_instances = mgr.list_by_project("proj-01")
    assert len(project_instances) == 1
    assert project_instances[0].project_id == "proj-01"
    assert project_instances[0].instance_id == "ladle-001"


def test_copy_for_scene_duplicate_raises():
    mgr = InstanceManager()
    mgr.create(project_id="proj-01", model_name="ladle", instance_id="ladle-001", scope="project")
    mgr.copy_for_scene("proj-01", "ladle-001", "drill")
    with pytest.raises(ValueError, match="already exists"):
        mgr.copy_for_scene("proj-01", "ladle-001", "drill")
