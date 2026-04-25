import asyncio
import json

import pytest
import websockets

from src.runtime.messaging import MessageEnvelope, SendResult
from src.worker.channels.jsonrpc_channel import JsonRpcChannel


@pytest.mark.anyio
async def test_jsonrpc_channel_send_uses_message_envelope():
    received = []

    async def handler(websocket):
        async for message in websocket:
            data = json.loads(message)
            received.append(data)
            if "id" in data:
                response = {"jsonrpc": "2.0", "id": data["id"], "result": {"acked": True}}
                await websocket.send(json.dumps(response))

    server = await websockets.serve(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    url = f"ws://127.0.0.1:{port}"

    channel = JsonRpcChannel(url)
    await channel.start(lambda envelope: None)
    for _ in range(50):
        if channel.is_ready():
            break
        await asyncio.sleep(0.05)
    assert channel.is_ready()

    result = await channel.send(
        MessageEnvelope(
            message_id="msg-1",
            world_id="factory-b",
            event_type="order.created",
            payload={"order_id": "O1"},
            source="world:factory-a",
        )
    )
    assert result == SendResult.SUCCESS
    assert len(received) == 1
    assert received[0]["method"] == "messageHub.publish"
    assert received[0]["params"]["message_id"] == "msg-1"
    assert received[0]["params"]["world_id"] == "factory-b"
    assert received[0]["params"]["event_type"] == "order.created"

    await channel.stop()
    server.close()
    await server.wait_closed()


@pytest.mark.anyio
async def test_jsonrpc_channel_send_retryable_when_not_ready():
    channel = JsonRpcChannel("ws://127.0.0.1:1")
    # Do not start
    result = await channel.send(
        MessageEnvelope(
            message_id="msg-2",
            world_id="factory-b",
            event_type="order.created",
            payload={"order_id": "O2"},
            source="world:factory-a",
        )
    )
    assert result == SendResult.RETRYABLE


@pytest.mark.anyio
async def test_jsonrpc_channel_receives_external_event():
    inbound_events: list[MessageEnvelope] = []

    async def handler(websocket):
        await asyncio.sleep(0.2)
        notification = {
            "jsonrpc": "2.0",
            "method": "notify.externalEvent",
            "params": {
                "message_id": "msg-3",
                "world_id": "factory-a",
                "event_type": "ext.event",
                "payload": {"val": 42},
                "source": "supervisor",
                "scope": "world",
                "target": None,
                "trace_id": "trace-1",
                "headers": {"x-origin": "test"},
            },
        }
        await websocket.send(json.dumps(notification))

    server = await websockets.serve(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    url = f"ws://127.0.0.1:{port}"

    channel = JsonRpcChannel(url)
    await channel.start(lambda envelope: inbound_events.append(envelope))

    for _ in range(50):
        if len(inbound_events) > 0:
            break
        await asyncio.sleep(0.05)

    await channel.stop()
    server.close()
    await server.wait_closed()

    assert len(inbound_events) == 1
    assert inbound_events[0] == MessageEnvelope(
        message_id="msg-3",
        world_id="factory-a",
        event_type="ext.event",
        payload={"val": 42},
        source="supervisor",
        scope="world",
        target=None,
        trace_id="trace-1",
        headers={"x-origin": "test"},
    )
