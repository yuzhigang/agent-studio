import asyncio
from unittest.mock import AsyncMock

import pytest

from src.supervisor.worker import WorkerController


@pytest.mark.anyio
async def test_end_to_end_list_instances():
    """Test the full flow: supervisor receives HTTP request, forwards to worker, worker responds."""
    gateway = WorkerController(base_dir="worlds")

    # Mock worker WebSocket
    mock_ws = AsyncMock()
    mock_ws.closed = False

    await gateway.register_worker(
        "wk-1", mock_ws, "sess-1", ["demo-world"]
    )

    # Start send_request in background
    request_task = asyncio.create_task(gateway.send_request("demo-world", {
        "jsonrpc": "2.0",
        "id": 42,
        "method": "world.instances.list",
        "params": {"world_id": "demo-world"},
    }))

    # Wait a tick for the request to be registered
    await asyncio.sleep(0.01)

    # Simulate worker response
    gateway._handle_response({
        "jsonrpc": "2.0",
        "id": 42,
        "result": {
            "instances": [
                {"id": "sensor-01", "model": "heartbeat", "state": "idle"},
            ]
        },
    })

    result = await request_task
    assert result["instances"][0]["id"] == "sensor-01"
