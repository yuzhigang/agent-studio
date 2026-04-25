from abc import ABC, abstractmethod
from typing import Callable

from src.runtime.messaging import MessageEnvelope, SendResult  # noqa: F401 — re-export


class Channel(ABC):
    @abstractmethod
    async def start(self, inbound_callback: Callable[[MessageEnvelope], None]) -> None:
        """Start the channel and begin receiving inbound messages."""
        ...

    @abstractmethod
    async def send(self, envelope: MessageEnvelope) -> SendResult:
        """Send a single message. Returns the send result."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully stop the channel."""
        ...

    @abstractmethod
    def is_ready(self) -> bool:
        """Return whether the channel is connected and ready to send."""
        ...
