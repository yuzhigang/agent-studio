import asyncio
import logging
from datetime import datetime, timedelta, timezone

from src.runtime.messaging.errors import PermanentDeliveryError, RetryableDeliveryError

logger = logging.getLogger(__name__)


class InboxProcessor:
    def __init__(
        self,
        hub,
        *,
        poll_interval: float = 1.0,
        batch_size: int = 100,
        max_retries: int = 10,
        retry_delay: float = 1.0,
    ):
        self._hub = hub
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            await self.run_once()
            await asyncio.sleep(self._poll_interval)

    async def run_once(self) -> None:
        store = self._hub._store
        if store is None:
            return
        self._expand_pending_messages()
        await self._deliver_pending()
        store.inbox_reconcile_statuses()

    def _expand_pending_messages(self) -> None:
        store = self._hub._store
        if store is None:
            return
        for envelope in store.inbox_read_pending(self._batch_size):
            world_ids = (
                self._hub.registered_worlds()
                if envelope.target_world == "*"
                else [envelope.target_world]
                if envelope.target_world is not None
                else []
            )
            store.inbox_create_deliveries(envelope.message_id, world_ids)
            if world_ids:
                store.inbox_mark_expanded(envelope.message_id)
            elif envelope.target_world is not None:
                store.inbox_mark_failed(envelope.message_id)

    async def _deliver_pending(self) -> None:
        store = self._hub._store
        if store is None:
            return
        deliveries = store.inbox_read_pending_deliveries(self._batch_size)
        if not deliveries:
            return

        by_world: dict[str, list] = {}
        for delivery in deliveries:
            by_world.setdefault(delivery.target_world, []).append(delivery)

        results = await asyncio.gather(*[
            self._deliver_for_world(world_id, world_deliveries)
            for world_id, world_deliveries in by_world.items()
        ], return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                logger.exception("Unexpected inbox delivery task failure", exc_info=result)

    async def _deliver_for_world(self, world_id: str, deliveries: list) -> None:
        store = self._hub._store
        for delivery in deliveries:
            try:
                envelope = store.inbox_load(delivery.message_id)
                receiver = self._hub.get_receiver(delivery.target_world)
                if receiver is None:
                    self._mark_receiver_unavailable(
                        message_id=delivery.message_id,
                        world_id=delivery.target_world,
                        error_count=delivery.error_count,
                    )
                    continue
                await receiver.receive(envelope)
            except KeyError:
                store.inbox_mark_delivery_dead(
                    delivery.message_id,
                    delivery.target_world,
                    error_count=delivery.error_count,
                    last_error="missing inbox message",
                )
            except RetryableDeliveryError as exc:
                self._mark_retry_or_dead(
                    message_id=delivery.message_id,
                    world_id=delivery.target_world,
                    error_count=delivery.error_count + 1,
                    last_error=str(exc),
                )
            except PermanentDeliveryError as exc:
                store.inbox_mark_delivery_dead(
                    delivery.message_id,
                    delivery.target_world,
                    error_count=delivery.error_count + 1,
                    last_error=str(exc),
                )
            except Exception as exc:
                logger.exception(
                    "Unexpected exception delivering message %s to world %s",
                    delivery.message_id,
                    delivery.target_world,
                )
                self._mark_retry_or_dead(
                    message_id=delivery.message_id,
                    world_id=delivery.target_world,
                    error_count=delivery.error_count + 1,
                    last_error=f"unexpected error: {exc}",
                )
            else:
                store.inbox_mark_delivery_delivered(
                    delivery.message_id,
                    delivery.target_world,
                )

    def _mark_receiver_unavailable(
        self,
        *,
        message_id: str,
        world_id: str,
        error_count: int,
    ) -> None:
        store = self._hub._store
        if store is None:
            return
        retry_after = (
            datetime.now(timezone.utc) + timedelta(seconds=self._retry_delay)
        ).isoformat()
        store.inbox_mark_delivery_retry(
            message_id,
            world_id,
            error_count=error_count,
            retry_after=retry_after,
            last_error="world receiver unavailable",
        )

    def _mark_retry_or_dead(
        self,
        *,
        message_id: str,
        world_id: str,
        error_count: int,
        last_error: str,
    ) -> None:
        store = self._hub._store
        if store is None:
            return
        if error_count >= self._max_retries:
            store.inbox_mark_delivery_dead(
                message_id,
                world_id,
                error_count=error_count,
                last_error=last_error,
            )
            return
        retry_after = (
            datetime.now(timezone.utc) + timedelta(seconds=self._retry_delay)
        ).isoformat()
        store.inbox_mark_delivery_retry(
            message_id,
            world_id,
            error_count=error_count,
            retry_after=retry_after,
            last_error=last_error,
        )
