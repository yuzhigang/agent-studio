import threading
from typing import Protocol

from src.runtime.messaging.envelope import MessageEnvelope
from src.runtime.messaging.inbox_processor import InboxProcessor
from src.runtime.messaging.outbox_processor import OutboxProcessor
from src.runtime.messaging.store import MessageStore
from src.runtime.messaging.world_receiver import WorldMessageReceiver


class MessageChannel(Protocol):
    async def start(self, inbound_callback) -> None: ...

    async def stop(self) -> None: ...

    async def send(self, envelope: MessageEnvelope): ...

    def is_ready(self) -> bool: ...


class MessageHub:
    def __init__(
        self,
        message_store: MessageStore | None,
        channel: MessageChannel | None,
        *,
        poll_interval: float = 1.0,
        batch_size: int = 100,
        max_retries: int = 10,
    ):
        self._store = message_store
        self._channel = channel
        self._lock = threading.RLock()
        self._receivers: dict[str, WorldMessageReceiver] = {}
        self._inbox_processor = (
            InboxProcessor(
                self,
                poll_interval=poll_interval,
                batch_size=batch_size,
                max_retries=max_retries,
            )
            if message_store is not None
            else None
        )
        self._outbox_processor = (
            OutboxProcessor(
                self,
                poll_interval=poll_interval,
                batch_size=batch_size,
                max_retries=max_retries,
            )
            if message_store is not None
            else None
        )

    def register_world(self, world_id: str, receiver: WorldMessageReceiver) -> None:
        with self._lock:
            self._receivers[world_id] = receiver

    def unregister_world(self, world_id: str, *, permanent: bool = False) -> None:
        with self._lock:
            self._receivers.pop(world_id, None)
        if permanent and self._store is not None:
            self._store.inbox_mark_world_deliveries_dead(
                world_id,
                last_error="world permanently removed",
            )
            self._store.inbox_reconcile_statuses()

    def get_receiver(self, world_id: str) -> WorldMessageReceiver | None:
        with self._lock:
            return self._receivers.get(world_id)

    def registered_worlds(self) -> list[str]:
        with self._lock:
            return sorted(self._receivers.keys())

    def on_inbound(self, envelope: MessageEnvelope) -> None:
        if self._store is None:
            return
        self._store.inbox_append(envelope)

    def enqueue_outbound(self, envelope: MessageEnvelope) -> None:
        if self._store is None:
            return
        self._store.outbox_append(envelope)

    async def start(self) -> None:
        if self._channel is not None:
            await self._channel.start(self.on_inbound)
        if self._inbox_processor is not None:
            self._inbox_processor.start()
        if self._outbox_processor is not None:
            self._outbox_processor.start()

    async def stop(self) -> None:
        if self._inbox_processor is not None:
            await self._inbox_processor.stop()
        if self._outbox_processor is not None:
            await self._outbox_processor.stop()
        if self._channel is not None:
            await self._channel.stop()
        if self._store is not None:
            self._store.close()

    def is_ready(self) -> bool:
        if self._channel is None:
            return True
        return self._channel.is_ready()
