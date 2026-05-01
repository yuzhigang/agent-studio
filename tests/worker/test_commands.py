import pytest
from src.worker.commands.world import world_stop, world_get_status
from src.worker.commands.instance import world_instances_list, world_instances_get
from src.worker.commands.scene import scene_start, scene_stop, world_scenes_list
from src.worker.commands.model import world_models_list, world_models_get
from src.worker.server.jsonrpc_ws import JsonRpcError


@pytest.fixture
def manager():
    from src.worker.manager import WorkerManager
    return WorkerManager()


@pytest.mark.anyio
async def test_world_stop_missing_bundle(manager):
    with pytest.raises(JsonRpcError) as exc:
        await world_stop(manager, None, {"world_id": "missing"})
    assert exc.value.code == -32004


@pytest.mark.anyio
async def test_world_get_status_ok(manager):
    mock_bundle = {
        "world_id": "w1",
        "scene_manager": type("SM", (), {
            "list_by_world": lambda self, wid: [{"scene_id": "s1"}]
        })(),
    }
    result = await world_get_status(manager, mock_bundle, {"world_id": "w1"})
    assert result["status"] == "running"
    assert result["scenes"] == ["s1"]


@pytest.mark.anyio
async def test_world_instances_list(manager):
    mock_bundle = {
        "world_id": "w1",
        "instance_manager": type("IM", (), {
            "list_by_world": lambda self, wid: [
                type("Inst", (), {
                    "instance_id": "i1",
                    "model_name": "robot",
                    "scope": "world",
                    "state": {"current": "idle"},
                    "lifecycle_state": "active",
                    "variables": {},
                    "attributes": {},
                })()
            ]
        })(),
    }
    result = await world_instances_list(manager, mock_bundle, {"world_id": "w1"})
    assert len(result["instances"]) == 1
    assert result["instances"][0]["id"] == "i1"


@pytest.mark.anyio
async def test_world_instances_get_found(manager):
    mock_inst = type("Inst", (), {
        "instance_id": "i1",
        "model_name": "robot",
        "scope": "world",
        "state": {"current": "idle"},
        "lifecycle_state": "active",
        "variables": {},
        "attributes": {},
        "bindings": {},
        "links": {},
        "memory": {},
        "audit": {},
    })()
    mock_bundle = {
        "world_id": "w1",
        "instance_manager": type("IM", (), {
            "get": lambda self, wid, iid: mock_inst if iid == "i1" else None
        })(),
    }
    result = await world_instances_get(manager, mock_bundle, {"world_id": "w1", "instance_id": "i1"})
    assert result["instance_id"] == "i1"


@pytest.mark.anyio
async def test_scene_start_already_running(manager):
    mock_bundle = {
        "world_id": "w1",
        "scene_manager": type("SM", (), {
            "get": lambda self, wid, sid: {"scene_id": sid} if sid == "s1" else None
        })(),
    }
    result = await scene_start(manager, mock_bundle, {"world_id": "w1", "scene_id": "s1"})
    assert result["status"] == "already_running"


@pytest.mark.anyio
async def test_world_scenes_list(manager):
    mock_bundle = {
        "world_id": "w1",
        "scene_manager": type("SM", (), {
            "list_by_world": lambda self, wid: [
                {"scene_id": "s1", "mode": "shared"},
                {"scene_id": "s2", "mode": "isolated"},
            ]
        })(),
        "instance_manager": type("IM", (), {
            "list_by_world": lambda self, wid: [
                type("Inst", (), {"scope": "world"})(),
                type("Inst", (), {"scope": "scene:s1"})(),
                type("Inst", (), {"scope": "scene:s1"})(),
                type("Inst", (), {"scope": "scene:s2"})(),
            ]
        })(),
    }
    result = await world_scenes_list(manager, mock_bundle, {"world_id": "w1"})
    assert len(result["scenes"]) == 2
    assert result["scenes"][0]["instance_count"] == 2
    assert result["scenes"][1]["instance_count"] == 1


@pytest.mark.anyio
async def test_world_models_list(manager, tmp_path):
    agents_dir = tmp_path / "agents" / "core" / "robot"
    agents_dir.mkdir(parents=True)
    (agents_dir / "model").mkdir()
    (agents_dir / "model" / "index.yaml").write_text("metadata:\n  name: Robot\n")

    mock_bundle = {"world_id": "w1", "world_dir": str(tmp_path)}
    result = await world_models_list(manager, mock_bundle, {"world_id": "w1"})
    assert len(result["models"]) == 1
    assert result["models"][0]["model_id"] == "core.robot"
