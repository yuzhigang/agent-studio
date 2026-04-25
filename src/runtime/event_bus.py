import logging
import threading

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self):
        self._subscribers: dict[str, list[tuple[str, str, callable]]] = {}
        # publish() can be called from sync runtime paths, so this stays thread-based.
        self._lock = threading.RLock()

    def register(self, instance_id: str, scope: str, event_type: str, handler: callable):
        with self._lock:
            self._subscribers.setdefault(event_type, []).append((instance_id, scope, handler))

    def unregister(self, instance_id: str, event_type: str | None = None):
        with self._lock:
            if event_type is not None:
                self._subscribers[event_type] = [
                    (iid, sc, h)
                    for iid, sc, h in self._subscribers.get(event_type, [])
                    if iid != instance_id
                ]
                return
            for et in list(self._subscribers.keys()):
                self._subscribers[et] = [
                    (iid, sc, h) for iid, sc, h in self._subscribers[et] if iid != instance_id
                ]

    def publish(
        self,
        event_type: str,
        payload: dict,
        source: str,
        scope: str,
        target: str | None = None,
    ):
        with self._lock:
            handlers = list(self._subscribers.get(event_type, []))
        for instance_id, inst_scope, handler in handlers:
            if target and instance_id != target:
                continue
            if not self._scope_matches(scope, inst_scope):
                continue
            try:
                handler(event_type, payload, source)
            except Exception:
                logger.exception("Handler failed for instance %s on event %s", instance_id, event_type)

    def _scope_matches(self, msg_scope: str, inst_scope: str) -> bool:
        if msg_scope == "world":
            return True
        return msg_scope == inst_scope


class EventBusRegistry:
    def __init__(self):
        self._buses: dict[str, EventBus] = {}
        self._lock = threading.Lock()

    def get_or_create(self, world_id: str) -> EventBus:
        with self._lock:
            if world_id not in self._buses:
                self._buses[world_id] = EventBus()
            return self._buses[world_id]

    def destroy(self, world_id: str):
        with self._lock:
            self._buses.pop(world_id, None)
