# tests/supervisor/test_server.py
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from src.supervisor.handlers.instances import handle_world_instances
from src.supervisor.worker import WorkerController


@pytest.fixture
async def app():
    gateway = WorkerController(base_dir="worlds")
    app = web.Application()
    app["gateway"] = gateway
    app["ws_port"] = 8001
    app["http_port"] = 8080
    app.router.add_get("/api/worlds/{world_id}/instances", handle_world_instances)
    return app


@pytest.fixture
async def client(app):
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    yield client
    await client.close()


@pytest.mark.anyio
async def test_list_instances_no_worker(client):
    resp = await client.get("/api/worlds/test-world/instances")
    assert resp.status == 404
    data = await resp.json()
    assert data["error"] == "world_not_found"


@pytest.mark.anyio
async def test_list_instances_success(client, app):
    gateway = app["gateway"]
    # Mock proxy_to_worker to return success without actual worker
    async def mock_proxy(world_id, method, params=None):
        return {"instances": [{"id": "inst-1", "model": "model-a", "scope": "world", "state": {"current": "idle"}, "lifecycle_state": "active"}]}
    gateway.proxy_to_worker = mock_proxy

    # Register a fake worker so get_worker_by_world returns something
    from unittest.mock import AsyncMock
    mock_ws = AsyncMock()
    await gateway.register_worker("wk-1", mock_ws, "sess-1", ["test-world"])

    resp = await client.get("/api/worlds/test-world/instances")
    assert resp.status == 200
    data = await resp.json()
    assert data["items"][0]["instance_id"] == "inst-1"
