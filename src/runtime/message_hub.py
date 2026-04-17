from __future__ import annotations

from typing import Callable

from src.runtime.event_bus import EventBus
from src.runtime.stores.base import MessageStore


class MessageHub:
    def __init__(self, message_store: MessageStore | None, channel):
        self._msg_store = message_store
        self._channel = channel
        self._subscriptions: dict[str, set[str]] = {}  # event_type -> {project_id, ...}
        self._projects: dict[str, tuple[EventBus, Callable]] = {}  # project_id -> (event_bus, hook)
        self._inbox_processor: InboxProcessor | None = None
        self._outbox_processor: OutboxProcessor | None = None

    def register_project(self, project_id: str, event_bus: EventBus, model_events: dict[str, dict]) -> None:
        if project_id in self._projects:
            return

        for event_type, meta in model_events.items():
            if meta.get("external", False):
                self._subscriptions.setdefault(event_type, set()).add(project_id)

        def hook(event_type: str, payload: dict, source: str, scope: str, target: str | None) -> None:
            if self._msg_store is None:
                return
            meta = model_events.get(event_type, {})
            if meta.get("external", False):
                self._msg_store.outbox_enqueue(event_type, payload, source, scope, target)

        event_bus.add_pre_publish_hook(hook)
        self._projects[project_id] = (event_bus, hook)

    def unregister_project(self, project_id: str) -> None:
        entry = self._projects.pop(project_id, None)
        if entry is None:
            return
        event_bus, hook = entry
        event_bus.remove_pre_publish_hook(hook)

        for event_type in list(self._subscriptions.keys()):
            self._subscriptions[event_type].discard(project_id)
            if not self._subscriptions[event_type]:
                del self._subscriptions[event_type]

    def registered_projects(self) -> list[str]:
        return list(self._projects.keys())

    def on_channel_message(self, event_type, payload, source, scope="project", target=None) -> None:
        if self._msg_store is not None:
            self._msg_store.inbox_enqueue(event_type, payload, source, scope, target)

    async def start(self) -> None:
        if self._channel is not None:
            await self._channel.start(self.on_channel_message)
        if self._msg_store is not None:
            from src.runtime.inbox_processor import InboxProcessor
            from src.runtime.outbox_processor import OutboxProcessor

            self._inbox_processor = InboxProcessor(self)
            self._outbox_processor = OutboxProcessor(self)
            self._inbox_processor.start()
            self._outbox_processor.start()

    async def stop(self) -> None:
        if self._inbox_processor is not None:
            await self._inbox_processor.stop()
            self._inbox_processor = None
        if self._outbox_processor is not None:
            await self._outbox_processor.stop()
            self._outbox_processor = None
        if self._channel is not None:
            await self._channel.stop()

    def publish(self, event_type, payload, source, scope="project", target=None) -> None:
        project_ids = self._subscriptions.get(event_type, set())
        if not project_ids:
            return
        for project_id in project_ids:
            event_bus, _ = self._projects.get(project_id, (None, None))
            if event_bus is not None:
                event_bus.publish(event_type, payload, source, scope, target, skip_hooks=True)

    def is_ready(self) -> bool:
        if self._channel is None:
            return True
        return self._channel.is_ready()
