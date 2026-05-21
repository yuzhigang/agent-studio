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
            # Find instance across all scopes (world + scenes)
            for candidate in self._im.list_by_world(world_id):
                if candidate.instance_id == source_instance_id:
                    inst = candidate
                    break
        # Ensure target is set for the three-scope model
        resolved_target = target if target is not None else world_id
        self._bus.publish(event_type, payload, source_instance_id, scope, resolved_target)

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
        # External ingress must provide target; default to source for agent scope
        resolved_target = target if target is not None else source
        self._bus.publish(
            event_type,
            payload,
            source,
            scope,
            resolved_target,
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
