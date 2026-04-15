import copy
from src.runtime.instance import Instance


def test_instance_creation():
    inst = Instance(
        instance_id="ladle-001",
        model_name="ladle",
        project_id="proj-01",
        scope="project",
        attributes={"capacity": 200},
        variables={"steelAmount": 180},
        links={"assignedCaster": "caster-03"},
    )
    assert inst.id == "ladle-001"
    assert inst.model_name == "ladle"
    assert inst.scope == "project"
    assert inst.variables["steelAmount"] == 180


def test_instance_deep_copy_isolation():
    inst = Instance(
        instance_id="ladle-001",
        model_name="ladle",
        project_id="proj-01",
        scope="project",
        variables={"steelAmount": 180, "nested": {"a": 1}},
        model={"geometry": {"radius": 5}, "material": "steel"},
    )
    clone = inst.deep_copy()
    clone.variables["steelAmount"] = 0
    clone.variables["nested"]["a"] = 99
    clone.model["geometry"]["radius"] = 10
    clone.model["material"] = "iron"
    assert inst.variables["steelAmount"] == 180
    assert inst.variables["nested"]["a"] == 1
    assert inst.model["geometry"]["radius"] == 5
    assert inst.model["material"] == "steel"
