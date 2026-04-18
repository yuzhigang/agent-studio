import uuid
from src.runtime.event_bus import EventBus
from src.runtime.stores.base import EventLogStore


class PersistentEventBus:
    def __init__(self, bus: EventBus, event_log_store: EventLogStore, world_id: str):
        self._bus = bus
        self._store = event_log_store
        self._world_id = world_id

    def publish(
        self,
        event_type: str,
        payload: dict,
        source: str,
        scope: str,
        target: str | None = None,
        *,
        persist: bool = True,
    ) -> None:
        self._bus.publish(event_type, payload, source, scope, target)
        if persist:
            event_id = uuid.uuid4().hex
            self._store.append(
                world_id=self._world_id,
                event_id=event_id,
                event_type=event_type,
                payload=payload,
                source=source,
                scope=scope,
            )

    def register(self, instance_id: str, scope: str, event_type: str, handler: callable):
        self._bus.register(instance_id, scope, event_type, handler)

    def unregister(self, instance_id: str):
        self._bus.unregister(instance_id)
