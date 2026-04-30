import pytest
import asyncio
from unittest.mock import AsyncMock

from src.supervisor.worker import WorkerController


@pytest.fixture
def controller():
    return WorkerController(base_dir="worlds")


@pytest.fixture
def mock_worker_ws():
    ws = AsyncMock()
    ws.closed = False
    return ws


@pytest.mark.anyio
async def test_send_request_success(controller, mock_worker_ws):
    await controller.register_worker("wk-1", mock_worker_ws, "sess-1", ["world-1"])

    async def delayed_response():
        await asyncio.sleep(0.05)
        controller._handle_response({
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"instances": [{"id": "inst-1"}]},
        })

    task = asyncio.create_task(delayed_response())

    result = await controller.send_request("world-1", {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "world.instances.list",
        "params": {"world_id": "world-1"},
    })

    assert result == {"instances": [{"id": "inst-1"}]}
    await task  # clean up


@pytest.mark.anyio
async def test_send_request_error_response(controller, mock_worker_ws):
    await controller.register_worker("wk-1", mock_worker_ws, "sess-1", ["world-1"])

    async def delayed_error():
        await asyncio.sleep(0.05)
        controller._handle_response({
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32004, "message": "World not loaded"},
        })

    asyncio.create_task(delayed_error())

    with pytest.raises(RuntimeError, match="World not loaded"):
        await controller.send_request("world-1", {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "world.instances.list",
            "params": {"world_id": "world-1"},
        })


@pytest.mark.anyio
async def test_send_request_no_worker(controller):
    with pytest.raises(RuntimeError, match="No worker running world"):
        await controller.send_request("unknown-world", {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "world.instances.list",
        })


@pytest.mark.anyio
async def test_send_request_timeout(controller, mock_worker_ws):
    await controller.register_worker("wk-1", mock_worker_ws, "sess-1", ["world-1"])

    with pytest.raises(asyncio.TimeoutError):
        await controller.send_request("world-1", {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "world.instances.list",
        }, timeout=0.01)


def test_handle_response_unknown_id(controller):
    # Should not raise
    controller._handle_response({
        "jsonrpc": "2.0",
        "id": "unknown-id",
        "result": {"instances": []},
    })
