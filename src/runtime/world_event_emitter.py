from __future__ import annotations

from src.runtime.event_bus import EventBus


class WorldEventEmitter:
    def __init__(self, event_bus: EventBus, instance_manager=None, message_sender=None):
        self._bus = event_bus
        self._im = instance_manager
        self._sender = message_sender

    def bind_instance_manager(self, instance_manager) -> None:
        self._im = instance_manager

    def bind_message_sender(self, message_sender) -> None:
        self._sender = message_sender

    def publish_from_instance(
        self,
        *,
        world_id: str,
        source_instance_id: str,
        scope: str,
        event_type: str,
        payload: dict,
        target: str | None = None,
    ) -> None:
        inst = None
        if self._im is not None:
            inst = self._im.get(world_id, source_instance_id, scope=scope)
        if inst is not None:
            inst._update_snapshot()
        self._bus.publish(event_type, payload, source_instance_id, scope, target)

    def publish_internal(
        self,
        *,
        event_type: str,
        payload: dict,
        source: str,
        scope: str,
        target: str | None = None,
        raise_on_error: bool = False,
    ) -> None:
        self._bus.publish(
            event_type,
            payload,
            source,
            scope,
            target,
            raise_on_error=raise_on_error,
        )

    def publish_external(
        self,
        *,
        event_type: str,
        payload: dict,
        scope: str = "world",
        target: str | None = None,
        trace_id: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        if self._sender is None:
            raise RuntimeError("WorldEventEmitter has no bound WorldMessageSender")
        return self._sender.send(
            event_type,
            payload,
            scope=scope,
            target=target,
            trace_id=trace_id,
            headers=headers,
        )
