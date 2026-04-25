from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.runtime.messaging.envelope import MessageEnvelope


@dataclass(slots=True)
class InboxDelivery:
    message_id: str
    target_world: str
    status: str
    error_count: int = 0
    retry_after: str | None = None
    last_error: str | None = None


class MessageStore(ABC):
    @abstractmethod
    def inbox_append(self, envelope: MessageEnvelope) -> None:
        raise NotImplementedError

    @abstractmethod
    def inbox_read_pending(self, limit: int) -> list[MessageEnvelope]:
        raise NotImplementedError

    @abstractmethod
    def inbox_load(self, message_id: str) -> MessageEnvelope:
        raise NotImplementedError

    @abstractmethod
    def inbox_mark_expanded(self, message_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def inbox_mark_completed(self, message_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def inbox_mark_failed(self, message_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def inbox_create_deliveries(self, message_id: str, target_worlds: list[str]) -> None:
        raise NotImplementedError

    @abstractmethod
    def inbox_read_pending_deliveries(self, limit: int) -> list[InboxDelivery]:
        raise NotImplementedError

    @abstractmethod
    def inbox_mark_delivery_delivered(self, message_id: str, target_world: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def inbox_mark_delivery_retry(
        self,
        message_id: str,
        target_world: str,
        *,
        error_count: int,
        retry_after: str | None,
        last_error: str | None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def inbox_mark_delivery_dead(
        self,
        message_id: str,
        target_world: str,
        *,
        error_count: int,
        last_error: str | None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def inbox_reconcile_statuses(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def inbox_mark_world_deliveries_dead(self, target_world: str, *, last_error: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def outbox_append(self, envelope: MessageEnvelope) -> None:
        raise NotImplementedError

    @abstractmethod
    def outbox_read_pending(self, limit: int) -> list[MessageEnvelope]:
        raise NotImplementedError

    @abstractmethod
    def outbox_get_error_count(self, message_id: str) -> int:
        raise NotImplementedError

    @abstractmethod
    def outbox_mark_sent(self, message_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def outbox_mark_retry(
        self,
        message_id: str,
        *,
        error_count: int,
        retry_after: str | None,
        last_error: str | None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def outbox_mark_dead(
        self,
        message_id: str,
        *,
        error_count: int,
        last_error: str | None,
    ) -> None:
        raise NotImplementedError
