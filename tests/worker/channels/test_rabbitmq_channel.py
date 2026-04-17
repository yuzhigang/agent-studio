import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.worker.channels.base import SendResult
from src.worker.channels.rabbitmq_channel import RabbitMQChannel


class FakeProcessContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass


class FakeIncomingMessage:
    def __init__(self, body_bytes):
        self.body = body_bytes

    def process(self):
        return FakeProcessContext()


@pytest.fixture
def mock_aio_pika():
    mock_exchange = MagicMock()
    mock_exchange.publish = AsyncMock()

    mock_queue = MagicMock()
    mock_queue.bind = AsyncMock()
    mock_queue.consume = AsyncMock(return_value="consumer-tag")

    mock_channel = MagicMock()
    mock_channel.is_closed = False
    mock_channel.close = AsyncMock()
    mock_channel.basic_cancel = AsyncMock()
    mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)
    mock_channel.declare_queue = AsyncMock(return_value=mock_queue)

    mock_conn = MagicMock()
    mock_conn.is_closed = False
    mock_conn.close = AsyncMock()
    mock_conn.channel = AsyncMock(return_value=mock_channel)

    with patch(
        "src.worker.channels.rabbitmq_channel.aio_pika.connect_robust",
        new_callable=AsyncMock,
    ) as mock_connect:
        mock_connect.return_value = mock_conn
        yield {
            "connect": mock_connect,
            "connection": mock_conn,
            "channel": mock_channel,
            "exchange": mock_exchange,
            "queue": mock_queue,
        }


@pytest.mark.anyio
async def test_rabbitmq_channel_start_stop(mock_aio_pika):
    channel = RabbitMQChannel("amqp://guest:guest@localhost/")
    await channel.start(lambda *args: None)
    assert channel.is_ready() is True

    await channel.stop()
    assert channel.is_ready() is False
    mock_aio_pika["connection"].close.assert_awaited_once()


@pytest.mark.anyio
async def test_rabbitmq_channel_send_success(mock_aio_pika):
    channel = RabbitMQChannel("amqp://guest:guest@localhost/")
    await channel.start(lambda *args: None)

    result = await channel.send(
        "order.shipped", {"id": "1"}, "inst-1", "project", None
    )
    assert result == SendResult.SUCCESS

    mock_exchange = mock_aio_pika["exchange"]
    mock_exchange.publish.assert_awaited_once()
    call_args = mock_exchange.publish.call_args
    message = call_args[0][0]
    routing_key = call_args[1]["routing_key"]
    assert routing_key == "order.shipped"
    body = json.loads(message.body.decode("utf-8"))
    assert body["event_type"] == "order.shipped"
    assert body["payload"] == {"id": "1"}

    await channel.stop()


@pytest.mark.anyio
async def test_rabbitmq_channel_send_retryable_when_not_ready():
    channel = RabbitMQChannel("amqp://guest:guest@localhost/")
    result = await channel.send(
        "order.shipped", {"id": "1"}, "inst-1", "project", None
    )
    assert result == SendResult.RETRYABLE


@pytest.mark.anyio
async def test_rabbitmq_channel_on_message_delivers_to_callback(mock_aio_pika):
    inbound_events = []

    channel = RabbitMQChannel("amqp://guest:guest@localhost/")
    await channel.start(
        lambda et, pl, src, sc, tgt: inbound_events.append((et, pl, src, sc, tgt))
    )

    body = json.dumps(
        {
            "event_type": "ext.event",
            "payload": {"val": 42},
            "source": "rmq",
            "scope": "project",
            "target": "tgt-1",
        }
    ).encode("utf-8")
    msg = FakeIncomingMessage(body)

    consume_callback = mock_aio_pika["queue"].consume.call_args[0][0]
    await consume_callback(msg)

    assert len(inbound_events) == 1
    assert inbound_events[0] == (
        "ext.event",
        {"val": 42},
        "rmq",
        "project",
        "tgt-1",
    )

    await channel.stop()
