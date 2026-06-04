import logging
import threading
import uuid

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self):
        self._subscribers: dict[str, list[tuple[str, str, str, callable]]] = {}
        # publish() can be called from sync runtime paths, so this stays thread-based.
        self._lock = threading.RLock()

    def register(self, instance_id: str, scope: str, event_type: str, handler: callable) -> str:
        subscription_id = str(uuid.uuid4())
        with self._lock:
            self._subscribers.setdefault(event_type, []).append(
                (subscription_id, instance_id, scope, handler)
            )
        return subscription_id

    def unregister(self, subscription_id: str):
        with self._lock:
            for et in list(self._subscribers.keys()):
                self._subscribers[et] = [
                    (sid, iid, sc, h)
                    for sid, iid, sc, h in self._subscribers[et]
                    if sid != subscription_id
                ]

    def publish(
        self,
        event_type: str,
        payload: dict,
        source: str,
        scope: str,
        target: str,
        raise_on_error: bool = False,
    ):
        if scope not in ("world", "agent", "scene"):
            raise ValueError(f"Invalid scope '{scope}': must be 'world', 'agent', or 'scene'")
        if not target:
            raise ValueError(f"target is required for scope='{scope}'")
        with self._lock:
            handlers = list(self._subscribers.get(event_type, []))
        delivered = 0
        for _, instance_id, inst_scope, handler in handlers:
            if not self._scope_matches(scope, target, inst_scope, instance_id):
                continue
            try:
                handler(event_type, payload, source)
                delivered += 1
            except Exception:
                if raise_on_error:
                    raise
                logger.exception("Handler failed for instance %s on event %s", instance_id, event_type)
        if delivered == 0:
            logger.debug(
                "Event %s (scope=%s, target=%s) delivered to 0 handlers",
                event_type, scope, target,
            )

    def _scope_matches(self, msg_scope: str, msg_target: str, inst_scope: str, instance_id: str) -> bool:
        """Three-scope routing:
        - scope="world" + target=worldId   → broadcast to all instances
        - scope="agent" + target=agentId   → unicast to the specific instance
        - scope="scene" + target=sceneId   → broadcast to instances in that scene
        """
        if msg_scope == "world":
            return True
        if msg_scope == "agent":
            return inst_scope == "world" and instance_id == msg_target
        if msg_scope == "scene":
            return inst_scope == f"scene:{msg_target}"
        return False


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
