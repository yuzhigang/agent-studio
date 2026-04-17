import asyncio
import logging
from datetime import datetime, timedelta, timezone

from src.worker.channels.base import SendResult

logger = logging.getLogger(__name__)


class OutboxProcessor:
    def __init__(
        self,
        message_hub,
        poll_interval: float = 1.0,
        batch_size: int = 100,
        max_retries: int = 10,
        max_retry_interval: float = 30.0,
    ):
        self._hub = message_hub
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._max_retries = max_retries
        self._max_retry_interval = max_retry_interval
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
        store = self._hub._msg_store
        channel = self._hub._channel
        while not self._stop_event.is_set():
            try:
                if channel is None:
                    await asyncio.sleep(self._poll_interval)
                    continue
                messages = store.outbox_read_pending(self._batch_size)
                for msg in messages:
                    if self._stop_event.is_set():
                        break
                    result = await channel.send(
                        event_type=msg["event_type"],
                        payload=msg["payload"],
                        source=msg["source"],
                        scope=msg["scope"],
                        target=msg.get("target"),
                    )
                    if result == SendResult.SUCCESS:
                        store.outbox_mark_sent(msg["id"])
                    elif result == SendResult.RETRYABLE:
                        error_count = min(msg.get("error_count", 0) + 1, self._max_retries)
                        backoff = min(2 ** error_count, self._max_retry_interval)
                        retry_dt = datetime.now(timezone.utc) + timedelta(seconds=backoff)
                        store.outbox_update_error(
                            msg["id"],
                            error_count=error_count,
                            retry_after=retry_dt.isoformat(),
                            last_error="retryable failure",
                        )
                    elif result == SendResult.PERMANENT:
                        store.outbox_update_error(
                            msg["id"],
                            error_count=self._max_retries,
                            retry_after=None,
                            last_error="permanent failure",
                        )
            except Exception:
                logger.exception("OutboxProcessor encountered an error during poll/send")
            await asyncio.sleep(self._poll_interval)
