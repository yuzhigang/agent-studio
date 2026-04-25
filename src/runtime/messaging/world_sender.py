from typing import Protocol
from uuid import uuid4

from src.runtime.messaging.envelope import MessageEnvelope


class _OutboundHub(Protocol):
    def enqueue_outbound(self, envelope: MessageEnvelope) -> None: ...


class WorldMessageSender:
    def __init__(
        self,
        world_id: str,
        hub: _OutboundHub | None,
        source: str,
    ):
        self._world_id = world_id
        self._hub = hub
        self._source = source

    def bind_hub(self, hub: _OutboundHub) -> None:
        self._hub = hub

    def send(
        self,
        event_type: str,
        payload: dict,
        *,
        target_world_id: str,
        scope: str = "world",
        target: str | None = None,
        trace_id: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        if self._hub is None:
            raise RuntimeError(
                f"WorldMessageSender for world '{self._world_id}' is not bound to a hub"
            )

        message_id = str(uuid4())
        envelope = MessageEnvelope(
            message_id=message_id,
            world_id=target_world_id,
            event_type=event_type,
            payload=payload,
            source=self._source,
            scope=scope,
            target=target,
            trace_id=trace_id,
            headers=headers or {},
        )
        self._hub.enqueue_outbound(envelope)
        return message_id
