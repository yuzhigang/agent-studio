import asyncio
import json

import pytest
import websockets

from src.worker.channels.jsonrpc_channel import JsonRpcChannel
from src.runtime.messaging import SendResult


@pytest.mark.anyio
async def test_jsonrpc_channel_send_success():
    received_messages = []

    async def handler(websocket):
        async for message in websocket:
            data = json.loads(message)
            received_messages.append(data)
            if "id" in data:
                response = {"jsonrpc": "2.0", "id": data["id"], "result": {"acked": True}}
                await websocket.send(json.dumps(response))

    server = await websockets.serve(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    url = f"ws://127.0.0.1:{port}"

    channel = JsonRpcChannel(url)
    await channel.start(lambda *args: None)
    for _ in range(50):
        if channel.is_ready():
            break
        await asyncio.sleep(0.05)
    assert channel.is_ready()

    result = await channel.send("order.shipped", {"id": "1"}, "inst-1", "world", None)
    assert result == SendResult.SUCCESS
    assert len(received_messages) == 1
    assert received_messages[0]["method"] == "messageHub.publish"
    assert received_messages[0]["params"]["event_type"] == "order.shipped"

    await channel.stop()
    server.close()
    await server.wait_closed()


@pytest.mark.anyio
async def test_jsonrpc_channel_send_retryable_when_not_ready():
    channel = JsonRpcChannel("ws://127.0.0.1:1")
    # Do not start
    result = await channel.send("order.shipped", {"id": "1"}, "inst-1", "world", None)
    assert result == SendResult.RETRYABLE


@pytest.mark.anyio
async def test_jsonrpc_channel_receives_external_event():
    inbound_events = []

    async def handler(websocket):
        await asyncio.sleep(0.2)
        notification = {
            "jsonrpc": "2.0",
            "method": "notify.externalEvent",
            "params": {
                "event_type": "ext.event",
                "payload": {"val": 42},
                "source": "supervisor",
                "scope": "world",
                "target": None,
            },
        }
        await websocket.send(json.dumps(notification))

    server = await websockets.serve(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    url = f"ws://127.0.0.1:{port}"

    channel = JsonRpcChannel(url)
    await channel.start(lambda et, pl, src, sc, tgt: inbound_events.append((et, pl, src, sc, tgt)))

    for _ in range(50):
        if len(inbound_events) > 0:
            break
        await asyncio.sleep(0.05)

    await channel.stop()
    server.close()
    await server.wait_closed()

    assert len(inbound_events) == 1
    assert inbound_events[0] == ("ext.event", {"val": 42}, "supervisor", "world", None)
