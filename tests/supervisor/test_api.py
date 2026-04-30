import json
import pytest
from aiohttp import web
from src.supervisor.worker import WorkerController


@pytest.fixture
def controller():
    return WorkerController(base_dir="test_worlds")


@pytest.fixture
def app(controller):
    app = web.Application()
    app["controller"] = controller
    app["ws_port"] = 8001
    app["http_port"] = 8080
    return app


@pytest.mark.anyio
async def test_get_workers_empty(app):
    from src.supervisor.handlers.workers import handle_workers
    request = type("Req", (), {"app": app})()
    response = await handle_workers(request)
    assert response.status == 200
    data = json.loads(response.text)
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.anyio
async def test_get_worker_worlds_not_found(app):
    from src.supervisor.handlers.workers import handle_worker_worlds
    request = type("Req", (), {"app": app, "match_info": {"worker_id": "nonexistent"}})()
    response = await handle_worker_worlds(request)
    assert response.status == 404


@pytest.mark.anyio
async def test_get_world_instances_with_filter(app):
    from src.supervisor.handlers.instances import handle_world_instances

    controller = app["controller"]
    async def mock_proxy(world_id, method, params=None):
        return {
            "instances": [
                {"id": "i1", "model": "robot", "scope": "world", "state": {"current": "idle"}, "lifecycle_state": "active"},
                {"id": "i2", "model": "car", "scope": "world", "state": {"current": "busy"}, "lifecycle_state": "active"},
            ]
        }
    controller.proxy_to_worker = mock_proxy
    controller._workers["worker1"] = type("W", (), {"worker_id": "worker1", "world_ids": ["w1"]})()
    controller._world_to_worker["w1"] = "worker1"

    request = type("Req", (), {
        "app": app,
        "match_info": {"world_id": "w1"},
        "query": {"model_id": "robot"},
    })()
    response = await handle_world_instances(request)
    assert response.status == 200
    data = json.loads(response.text)
    assert len(data["items"]) == 1
    assert data["items"][0]["instance_id"] == "i1"
    assert data["items"][0]["state"] == "idle"


@pytest.mark.anyio
async def test_post_world_stop_triggers_broadcast(app):
    from src.supervisor.handlers.worlds import handle_world_stop

    controller = app["controller"]
    broadcasts = []
    async def mock_broadcast(msg):
        broadcasts.append(msg)
    controller._broadcast = mock_broadcast
    controller._world_status_cache["w1"] = {"status": "running"}

    async def mock_proxy(world_id, method, params=None):
        return {"status": "stopped"}
    controller.proxy_to_worker = mock_proxy
    controller._workers["worker1"] = type("W", (), {"worker_id": "worker1"})()
    controller._world_to_worker["w1"] = "worker1"

    request = type("Req", (), {"app": app, "match_info": {"world_id": "w1"}})()
    response = await handle_world_stop(request)
    assert response.status == 200
    assert len(broadcasts) == 1
    assert broadcasts[0]["method"] == "notify.world.status_changed"


@pytest.mark.anyio
async def test_get_world_detail_worker_not_found(app):
    from src.supervisor.handlers.worlds import handle_world_detail
    request = type("Req", (), {"app": app, "match_info": {"world_id": "w1"}})()
    response = await handle_world_detail(request)
    assert response.status == 404
