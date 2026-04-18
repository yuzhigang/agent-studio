import copy
from src.runtime.instance import Instance


def test_instance_creation():
    inst = Instance(
        instance_id="ladle-001",
        model_name="ladle",
        world_id="world-01",
        scope="world",
        attributes={"capacity": 200},
        variables={"steelAmount": 180},
        links={"assignedCaster": "caster-03"},
    )
    assert inst.id == "ladle-001"
    assert inst.model_name == "ladle"
    assert inst.scope == "world"
    assert inst.variables["steelAmount"] == 180
    assert inst.attributes["capacity"] == 200
    assert inst.links["assignedCaster"] == "caster-03"
    assert inst.memory == {}
    assert inst.state == {"current": None, "enteredAt": None}
    assert inst.audit == {"version": 0, "updatedAt": None, "lastEventId": None}


def test_instance_update_snapshot_with_audit_fields():
    inst = Instance(
        instance_id="ladle-001",
        model_name="ladle",
        world_id="proj-01",
        scope="world",
        state={"current": "idle", "enteredAt": "2024-01-01T00:00:00Z"},
        variables={"temperature": 1500, "weight": 200},
        attributes={"capacity": 300},
        model={
            "variables": {
                "temperature": {"type": "number", "audit": True},
                "weight": {"type": "number", "audit": True},
                "operator": {"type": "string"},
            },
            "attributes": {
                "capacity": {"type": "number", "audit": True},
                "material": {"type": "string"},
            },
            "derivedProperties": {
                "loadRatio": {"type": "number", "audit": True},
            },
        },
    )
    inst._update_snapshot()
    assert inst.snapshot["temperature"] == 1500
    assert inst.snapshot["weight"] == 200
    assert inst.snapshot["capacity"] == 300
    assert inst.snapshot["loadRatio"] is None
    assert "operator" not in inst.snapshot
    assert "material" not in inst.snapshot

    # Verify world_state property assembles correctly
    ws = inst.world_state
    assert ws["id"] == "ladle-001"
    assert ws["state"] == "idle"
    assert ws["updated_at"] == "2024-01-01T00:00:00Z"
    assert ws["lifecycle_state"] == "active"
    assert ws["snapshot"]["temperature"] == 1500


def test_instance_update_snapshot_caches_audit_fields():
    inst = Instance(
        instance_id="ladle-001",
        model_name="ladle",
        world_id="proj-01",
        scope="world",
        variables={"temperature": 1500},
        model={
            "variables": {"temperature": {"type": "number", "audit": True}}
        },
    )
    assert not inst._audit_fields
    inst._update_snapshot()
    assert "temperature" in inst._audit_fields
    assert inst._audit_fields["temperature"] == "variables"

    # Change variable and update again - should use cached fields
    inst.variables["temperature"] = 1600
    inst._update_snapshot()
    assert inst.snapshot["temperature"] == 1600


def test_instance_deep_copy_isolation():
    inst = Instance(
        instance_id="ladle-001",
        model_name="ladle",
        world_id="world-01",
        scope="world",
        variables={"steelAmount": 180, "nested": {"a": 1}},
        model={"geometry": {"radius": 5}, "material": "steel"},
    )
    clone = inst.deep_copy()
    assert clone.instance_id == inst.instance_id
    assert clone.model_name == inst.model_name
    assert clone.world_id == inst.world_id
    assert clone.scope == inst.scope
    clone.variables["steelAmount"] = 0
    clone.variables["nested"]["a"] = 99
    clone.model["geometry"]["radius"] = 10
    clone.model["material"] = "iron"
    assert inst.variables["steelAmount"] == 180
    assert inst.variables["nested"]["a"] == 1
    assert inst.model["geometry"]["radius"] == 5
    assert inst.model["material"] == "steel"
