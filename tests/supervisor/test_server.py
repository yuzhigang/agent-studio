import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from src.supervisor.server import _handle_list_instances
from src.supervisor.worker import WorkerController


class TestListInstances(AioHTTPTestCase):
    async def get_application(self):
        gateway = WorkerController(base_dir="worlds")
        app = web.Application()
        app["gateway"] = gateway
        app["ws_port"] = 8001
        app["http_port"] = 8080
        app.router.add_get("/api/worlds/{world_id}/instances", _handle_list_instances)
        return app

    @unittest_run_loop
    async def test_list_instances_no_worker(self):
        resp = await self.client.request("GET", "/api/worlds/test-world/instances")
        assert resp.status == 404
        data = await resp.json()
        assert "error" in data
