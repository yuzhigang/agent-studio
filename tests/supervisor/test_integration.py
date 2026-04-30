import json
import pytest
from aiohttp import web
from src.supervisor.worker import WorkerController
from src.supervisor.handlers.workers import handle_workers


@pytest.mark.anyio
async def test_full_api_flow():
    gateway = WorkerController(base_dir="test_worlds")
    app = web.Application()
    app["gateway"] = gateway
    app["ws_port"] = 8001
    app["http_port"] = 8080

    request = type("Req", (), {"app": app})()
    response = await handle_workers(request)
    assert response.status == 200
    data = json.loads(response.text)
    assert "items" in data
    assert "total" in data
