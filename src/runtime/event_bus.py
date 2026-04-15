import threading


class EventBus:
    def __init__(self):
        self._subscribers: dict[str, list[tuple[str, str, callable]]] = {}
        self._lock = threading.RLock()

    def register(self, instance_id: str, scope: str, event_type: str, handler: callable):
        with self._lock:
            self._subscribers.setdefault(event_type, []).append((instance_id, scope, handler))

    def unregister(self, instance_id: str):
        with self._lock:
            for event_type in list(self._subscribers.keys()):
                self._subscribers[event_type] = [
                    (iid, sc, h) for iid, sc, h in self._subscribers[event_type] if iid != instance_id
                ]

    def publish(self, event_type: str, payload: dict, source: str, scope: str, target: str | None = None):
        with self._lock:
            handlers = list(self._subscribers.get(event_type, []))
        for instance_id, inst_scope, handler in handlers:
            if target and instance_id != target:
                continue
            if not self._scope_matches(scope, inst_scope):
                continue
            handler(event_type, payload, source)

    def _scope_matches(self, msg_scope: str, inst_scope: str) -> bool:
        if msg_scope == "project":
            return True
        return msg_scope == inst_scope


class EventBusRegistry:
    def __init__(self):
        self._buses: dict[str, EventBus] = {}
        self._lock = threading.Lock()

    def get_or_create(self, project_id: str) -> EventBus:
        with self._lock:
            if project_id not in self._buses:
                self._buses[project_id] = EventBus()
            return self._buses[project_id]

    def destroy(self, project_id: str):
        with self._lock:
            self._buses.pop(project_id, None)
