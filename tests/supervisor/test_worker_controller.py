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
    # Register a mock worker
    await controller.register_worker(
        "wk-1", mock_worker_ws, "sess-1", ["world-1"]
    )

    # Simulate worker responding in background
    async def delayed_response():
        await asyncio.sleep(0.05)
        # Simulate the response handler being called
        future = list(controller._pending_requests.values())[0]
        future.set_result({"instances": [{"id": "inst-1"}]})

    asyncio.create_task(delayed_response())

    result = await controller.send_request("world-1", {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "world.instances.list",
        "params": {"world_id": "world-1"},
    })

    assert result == {"instances": [{"id": "inst-1"}]}
