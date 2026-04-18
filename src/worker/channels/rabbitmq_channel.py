import json
from typing import Callable

import aio_pika
from aio_pika import DeliveryMode, ExchangeType

from src.worker.channels.base import Channel, SendResult


class RabbitMQChannel(Channel):
    """RabbitMQ channel implementation using aio-pika."""

    def __init__(
        self,
        amqp_url: str,
        exchange_name: str = "agent-studio",
        queue_name: str | None = None,
        routing_key: str = "#",
    ):
        self._amqp_url = amqp_url
        self._exchange_name = exchange_name
        self._queue_name = queue_name or ""
        self._routing_key = routing_key
        self._inbound_callback: Callable | None = None
        self._connection: aio_pika.RobustConnection | None = None
        self._channel: aio_pika.RobustChannel | None = None
        self._exchange: aio_pika.Exchange | None = None
        self._consumer_tag: str | None = None

    async def start(
        self, inbound_callback: Callable[[str, dict, str, str, str | None], None]
    ) -> None:
        self._inbound_callback = inbound_callback
        self._connection = await aio_pika.connect_robust(self._amqp_url)
        self._channel = await self._connection.channel()
        self._exchange = await self._channel.declare_exchange(
            self._exchange_name, ExchangeType.TOPIC, durable=True
        )
        queue = await self._channel.declare_queue(self._queue_name, durable=True)
        await queue.bind(self._exchange, routing_key=self._routing_key)
        self._consumer_tag = await queue.consume(self._on_message)

    async def stop(self) -> None:
        if self._channel is not None and not self._channel.is_closed:
            if self._consumer_tag is not None:
                try:
                    await self._channel.basic_cancel(self._consumer_tag)
                except Exception:
                    pass
            await self._channel.close()
        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()
        self._channel = None
        self._connection = None
        self._exchange = None
        self._consumer_tag = None

    def is_ready(self) -> bool:
        if self._connection is None or self._channel is None:
            return False
        return not self._connection.is_closed and not self._channel.is_closed

    async def send(
        self,
        event_type: str,
        payload: dict,
        source: str,
        scope: str,
        target: str | None,
    ) -> SendResult:
        if not self.is_ready() or self._exchange is None:
            return SendResult.RETRYABLE
        body = json.dumps(
            {
                "event_type": event_type,
                "payload": payload,
                "source": source,
                "scope": scope,
                "target": target,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        message = aio_pika.Message(
            body=body,
            content_type="application/json",
            delivery_mode=DeliveryMode.PERSISTENT,
        )
        try:
            await self._exchange.publish(message, routing_key=event_type)
            return SendResult.SUCCESS
        except Exception:
            return SendResult.RETRYABLE

    async def _on_message(self, message: aio_pika.IncomingMessage) -> None:
        async with message.process():
            try:
                data = json.loads(message.body.decode("utf-8"))
                if self._inbound_callback is not None:
                    self._inbound_callback(
                        data.get("event_type", ""),
                        data.get("payload", {}),
                        data.get("source", ""),
                        data.get("scope", "world"),
                        data.get("target"),
                    )
            except Exception:
                pass
