from abc import ABC, abstractmethod
from enum import Enum
from typing import Callable


class SendResult(Enum):
    SUCCESS = "success"
    RETRYABLE = "retryable"
    PERMANENT = "permanent"


class Channel(ABC):
    @abstractmethod
    async def start(self, inbound_callback: Callable[[str, dict, str, str, str | None], None]) -> None:
        """Start the channel and begin receiving inbound messages."""
        ...

    @abstractmethod
    async def send(
        self,
        event_type: str,
        payload: dict,
        source: str,
        scope: str,
        target: str | None,
    ) -> SendResult:
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
