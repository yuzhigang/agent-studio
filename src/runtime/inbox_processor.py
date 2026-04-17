import asyncio
import logging

logger = logging.getLogger(__name__)


class InboxProcessor:
    def __init__(self, message_hub, poll_interval: float = 1.0, batch_size: int = 100):
        self._hub = message_hub
        self._poll_interval = poll_interval
        self._batch_size = batch_size
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
        while not self._stop_event.is_set():
            try:
                messages = store.inbox_read_pending(self._batch_size)
                for msg in messages:
                    if self._stop_event.is_set():
                        break
                    success = self._distribute(msg)
                    if success:
                        store.inbox_mark_processed(msg["id"])
            except Exception:
                logger.exception("InboxProcessor encountered an error during poll/distribute")
            await asyncio.sleep(self._poll_interval)

    def _distribute(self, msg: dict) -> bool:
        event_type = msg["event_type"]
        project_ids = self._hub._subscriptions.get(event_type, set())
        if not project_ids:
            return True
        target = msg.get("target")
        if target is not None:
            if target not in project_ids:
                return True
            project_ids = [target]
        any_failed = False
        for project_id in project_ids:
            event_bus, _ = self._hub._projects.get(project_id, (None, None))
            if event_bus is None:
                continue
            try:
                self._hub.publish(
                    event_type,
                    msg["payload"],
                    msg["source"],
                    msg["scope"],
                    target,
                )
            except Exception:
                any_failed = True
        return not any_failed
