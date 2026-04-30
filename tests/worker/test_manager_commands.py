import pytest
from src.worker.manager import WorkerManager
from src.worker.server.jsonrpc_ws import JsonRpcError


@pytest.fixture
def manager_with_world():
    mgr = WorkerManager()
    mgr.worlds["test-world"] = {
        "world_id": "test-world",
        "instance_manager": MockInstanceManager(),
    }
    return mgr


class MockInstanceManager:
    def list_by_world(self, world_id):
        from src.runtime.instance import Instance
        return [
            Instance(
                instance_id="inst-1",
                model_name="model-a",
                world_id=world_id,
                scope="world",
                state={"current": "idle", "enteredAt": "2026-04-30T00:00:00"},
                lifecycle_state="active",
                variables={"count": 0},
                attributes={"capacity": 100},
            ),
        ]


@pytest.mark.anyio
async def test_world_instances_list(manager_with_world):
    result = await manager_with_world.handle_command(
        "world.instances.list", {"world_id": "test-world"}
    )
    assert "instances" in result
    assert len(result["instances"]) == 1
    inst = result["instances"][0]
    assert inst["id"] == "inst-1"
    assert inst["model"] == "model-a"
    assert inst["state"] == "idle"
    assert inst["scope"] == "world"
    assert inst["lifecycle_state"] == "active"


@pytest.mark.anyio
async def test_world_instances_list_world_not_loaded():
    mgr = WorkerManager()
    with pytest.raises(JsonRpcError, match="World test-world not loaded"):
        await mgr.handle_command("world.instances.list", {"world_id": "test-world"})
