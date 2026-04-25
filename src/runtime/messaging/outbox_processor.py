import asyncio
import logging
from datetime import datetime, timedelta, timezone

from src.runtime.messaging.send_result import SendResult

logger = logging.getLogger(__name__)


class OutboxProcessor:
    def __init__(
        self,
        hub,
        *,
        poll_interval: float = 1.0,
        batch_size: int = 100,
        max_retries: int = 10,
        retry_delay: float = 1.0,
        max_concurrency: int = 8,
    ):
        self._hub = hub
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._max_concurrency = max_concurrency
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
        channel = self._hub._channel
        if store is None or channel is None:
            return
        envelopes = store.outbox_read_pending(self._batch_size)
        if not envelopes:
            return

        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def _send_one(envelope):
            async with semaphore:
                try:
                    result = await channel.send(envelope)
                except Exception as exc:
                    logger.exception(
                        "Unexpected exception sending outbox message %s",
                        envelope.message_id,
                    )
                    result = SendResult.RETRYABLE
                if result is SendResult.SUCCESS:
                    store.outbox_mark_sent(envelope.message_id)
                elif result is SendResult.RETRYABLE:
                    error_count = store.outbox_get_error_count(envelope.message_id) + 1
                    if error_count >= self._max_retries:
                        store.outbox_mark_dead(
                            envelope.message_id,
                            error_count=error_count,
                            last_error="retryable failure",
                        )
                        return
                    retry_after = (
                        datetime.now(timezone.utc) + timedelta(seconds=self._retry_delay)
                    ).isoformat()
                    store.outbox_mark_retry(
                        envelope.message_id,
                        error_count=error_count,
                        retry_after=retry_after,
                        last_error="retryable failure",
                    )
                else:
                    store.outbox_mark_dead(
                        envelope.message_id,
                        error_count=self._max_retries,
                        last_error="permanent failure",
                    )

        results = await asyncio.gather(
            *[_send_one(envelope) for envelope in envelopes],
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                logger.exception("Unexpected outbox worker failure", exc_info=result)
