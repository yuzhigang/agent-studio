import pytest
from aiohttp import web
from unittest.mock import AsyncMock


@pytest.fixture
def mock_controller():
    controller = AsyncMock()
    controller.proxy_to_worker = AsyncMock(return_value={"acked": True})
    return controller


@pytest.fixture
def app(mock_controller):
    app = web.Application()
    app["controller"] = mock_controller
    return app


@pytest.mark.anyio
async def test_post_single_event(app, aiohttp_client, mock_controller):
    from src.supervisor.handlers.events import handle_post_event
    app.router.add_post("/api/worlds/{world_id}/events", handle_post_event)
    client = await aiohttp_client(app)
    resp = await client.post("/api/worlds/demo-world/events", json={
        "event_type": "tick",
        "payload": {"temperature": 85},
        "scope": "world"
    })
    assert resp.status == 200
    data = await resp.json()
    assert data["acked"] is True
    mock_controller.proxy_to_worker.assert_awaited_once()


@pytest.mark.anyio
async def test_post_batch_events(app, aiohttp_client, mock_controller):
    from src.supervisor.handlers.events import handle_post_batch_events
    app.router.add_post("/api/worlds/{world_id}/events/batch", handle_post_batch_events)
    client = await aiohttp_client(app)
    resp = await client.post("/api/worlds/demo-world/events/batch", json={
        "events": [
            {"event_type": "beat", "payload": {}, "scope": "world"},
            {"event_type": "tick", "payload": {"temperature": 85}, "scope": "world"}
        ]
    })
    assert resp.status == 200
    data = await resp.json()
    assert data["count"] == 2


@pytest.mark.anyio
async def test_get_outbox(app, aiohttp_client, mock_controller):
    from src.supervisor.handlers.events import handle_get_outbox
    mock_controller.proxy_to_worker = AsyncMock(return_value={"items": [], "total": 0})
    app.router.add_get("/api/worlds/{world_id}/outbox", handle_get_outbox)
    client = await aiohttp_client(app)
    resp = await client.get("/api/worlds/demo-world/outbox?limit=10")
    assert resp.status == 200
    data = await resp.json()
    assert data["total"] == 0
