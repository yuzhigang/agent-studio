from typing import Protocol

from src.runtime.messaging.envelope import MessageEnvelope


class WorldMessageReceiver(Protocol):
    async def receive(self, envelope: MessageEnvelope) -> None: ...
