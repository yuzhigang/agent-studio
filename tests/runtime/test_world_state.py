import pytest
from src.runtime.world_state import WorldState
from src.runtime.instance_manager import InstanceManager


def test_world_state_snapshot_groups_by_model_name():
    mgr = InstanceManager()
    inst1 = mgr.create(
        world_id="proj-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="world",
        state={"current": "idle", "enteredAt": "2024-01-01T00:00:00Z"},
        variables={"temperature": 1500},
        model={
            "variables": {"temperature": {"type": "number", "audit": True}}
        },
    )
    inst1._update_snapshot()

    inst2 = mgr.create(
        world_id="proj-01",
        model_name="ladle",
        instance_id="ladle-002",
        scope="world",
        state={"current": "moving", "enteredAt": "2024-01-01T01:00:00Z"},
        variables={"temperature": 1600},
        model={
            "variables": {"temperature": {"type": "number", "audit": True}}
        },
    )
    inst2._update_snapshot()

    inst3 = mgr.create(
        world_id="proj-01",
        model_name="crane",
        instance_id="crane-001",
        scope="world",
        state={"current": "lifting", "enteredAt": "2024-01-01T00:30:00Z"},
        variables={"loadWeight": 5000},
        model={
            "variables": {"loadWeight": {"type": "number", "audit": True}}
        },
    )
    inst3._update_snapshot()

    # Create an archived instance that should be excluded
    inst4 = mgr.create(
        world_id="proj-01",
        model_name="ladle",
        instance_id="ladle-003",
        scope="world",
        state={"current": "idle", "enteredAt": "2024-01-01T02:00:00Z"},
        variables={"temperature": 1700},
        model={
            "variables": {"temperature": {"type": "number", "audit": True}}
        },
    )
    inst4._update_snapshot()
    mgr.transition_lifecycle("proj-01", "ladle-003", "archived")

    ws = WorldState(mgr, "proj-01")
    snapshot = ws.snapshot()

    assert "ladle" in snapshot
    assert "crane" in snapshot
    assert len(snapshot["ladle"]) == 2
    assert len(snapshot["crane"]) == 1

    ladle_ids = {item["id"] for item in snapshot["ladle"]}
    assert ladle_ids == {"ladle-001", "ladle-002"}
    assert snapshot["crane"][0]["id"] == "crane-001"

    # Verify structure
    item = snapshot["ladle"][0]
    assert "state" in item
    assert "updated_at" in item
    assert "lifecycle_state" in item
    assert "snapshot" in item


def test_world_state_get_model():
    mgr = InstanceManager()
    mgr.create(
        world_id="proj-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="world",
        state={"current": "idle", "enteredAt": "2024-01-01T00:00:00Z"},
        variables={"temperature": 1500},
        model={"variables": {"temperature": {"type": "number", "audit": True}}},
    )
    mgr.create(
        world_id="proj-01",
        model_name="ladle",
        instance_id="ladle-002",
        scope="world",
        state={"current": "moving", "enteredAt": "2024-01-01T01:00:00Z"},
        variables={"temperature": 1600},
        model={"variables": {"temperature": {"type": "number", "audit": True}}},
    )
    mgr.create(
        world_id="proj-01",
        model_name="crane",
        instance_id="crane-001",
        scope="world",
        state={"current": "lifting", "enteredAt": "2024-01-01T00:30:00Z"},
        variables={"loadWeight": 5000},
        model={"variables": {"loadWeight": {"type": "number", "audit": True}}},
    )

    ws = WorldState(mgr, "proj-01")
    ladle_list = ws.get_model("ladle")
    assert len(ladle_list) == 2
    assert {item["id"] for item in ladle_list} == {"ladle-001", "ladle-002"}

    crane_list = ws.get_model("crane")
    assert len(crane_list) == 1
    assert crane_list[0]["id"] == "crane-001"

    assert ws.get_model("nonexistent") == []


def test_world_state_get_instance():
    mgr = InstanceManager()
    mgr.create(
        world_id="proj-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="world",
        state={"current": "idle", "enteredAt": "2024-01-01T00:00:00Z"},
        variables={"temperature": 1500},
        model={"variables": {"temperature": {"type": "number", "audit": True}}},
    )

    ws = WorldState(mgr, "proj-01")
    item = ws.get_instance("ladle-001")
    assert item is not None
    assert item["id"] == "ladle-001"
    assert item["state"] == "idle"
    assert item["snapshot"]["temperature"] == 1500

    assert ws.get_instance("nonexistent") is None


def test_world_state_get_instance_state():
    mgr = InstanceManager()
    mgr.create(
        world_id="proj-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="world",
        state={"current": "idle", "enteredAt": "2024-01-01T00:00:00Z"},
        variables={"temperature": 1500},
        model={"variables": {"temperature": {"type": "number", "audit": True}}},
    )

    ws = WorldState(mgr, "proj-01")
    assert ws.get_instance_state("ladle-001") == "idle"
    assert ws.get_instance_state("nonexistent") is None
