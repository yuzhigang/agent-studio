# src/runtime/triggers/timer_trigger.py
"""
TimerTrigger: delay, interval, and cron triggers driven by asyncio.

Does NOT use threading.Timer. Schedules asyncio tasks so that all callback
execution stays on the same event-loop thread as the rest of the runtime.
"""
import asyncio
from datetime import datetime

from croniter import croniter

from src.runtime.trigger_registry import Trigger


class TimerScheduler:
    """asyncio-backed timer scheduler. Replaces threading.Timer."""

    def __init__(self):
        self._tasks: dict[str, asyncio.Task] = {}
        self._counter = 0

    def schedule(self, delay_ms: float, callback, *, repeat: bool = False, interval_ms: float | None = None) -> str:
        self._counter += 1
        timer_id = f"timer_{self._counter}"

        async def _runner():
            try:
                await asyncio.sleep(delay_ms / 1000.0)
                if timer_id not in self._tasks:
                    return
                try:
                    callback()
                except Exception:
                    pass
                while repeat and timer_id in self._tasks:
                    await asyncio.sleep(interval_ms / 1000.0)
                    if timer_id not in self._tasks:
                        return
                    try:
                        callback()
                    except Exception:
                        pass
            except asyncio.CancelledError:
                pass

        task = asyncio.ensure_future(_runner())
        self._tasks[timer_id] = task
        return timer_id

    def schedule_cron(self, cron_expr: str, callback, *, count: int = -1) -> str:
        """Schedule a callback to fire according to a cron expression.

        The callback is invoked each time the cron expression matches the
        current local time. If count > 0, it stops after that many firings.
        """
        self._counter += 1
        timer_id = f"timer_{self._counter}"

        async def _runner():
            fired = 0
            try:
                while timer_id in self._tasks:
                    try:
                        itr = croniter(cron_expr, datetime.now())
                        next_time = itr.get_next(datetime)
                    except (ValueError, KeyError):
                        break

                    wait_seconds = (next_time - datetime.now()).total_seconds()
                    if wait_seconds <= 0:
                        wait_seconds = 0.001
                    await asyncio.sleep(wait_seconds)

                    if timer_id not in self._tasks:
                        return

                    try:
                        callback()
                    except Exception:
                        pass

                    fired += 1
                    if count > 0 and fired >= count:
                        self.cancel(timer_id)
                        return
            except asyncio.CancelledError:
                pass

        task = asyncio.ensure_future(_runner())
        self._tasks[timer_id] = task
        return timer_id

    def cancel(self, timer_id: str) -> None:
        task = self._tasks.pop(timer_id, None)
        if task is not None:
            task.cancel()

    def cancel_all(self) -> None:
        for timer_id in list(self._tasks.keys()):
            self.cancel(timer_id)


class TimerTrigger(Trigger):
    trigger_types = {"delay", "interval", "cron"}

    def __init__(self, scheduler: TimerScheduler | None = None):
        self._scheduler = scheduler or TimerScheduler()
        self._timers: dict[str, str] = {}   # entry.id -> timer_id
        self._entries: dict[str, dict] = {}  # timer_id -> {"entry": entry, "instance": instance}

    def on_registered(self, entry):
        trigger = entry.trigger
        trigger_type = trigger["type"]

        if trigger_type == "delay":
            delay_ms = trigger.get("delay", 0)
            timer_id = self._scheduler.schedule(
                delay_ms,
                lambda e=entry: e.callback(e.instance),
            )
            self._timers[entry.id] = timer_id
            self._entries[timer_id] = {"entry": entry, "instance": entry.instance}

        elif trigger_type == "interval":
            interval_ms = trigger.get("interval", 1000)
            count = trigger.get("count", -1)
            fired = [0]

            def callback():
                fired[0] += 1
                entry.callback(entry.instance)
                if count > 0 and fired[0] >= count:
                    tid = self._timers.get(entry.id)
                    if tid is not None:
                        self._scheduler.cancel(tid)
                        self._timers.pop(entry.id, None)
                        self._entries.pop(tid, None)

            timer_id = self._scheduler.schedule(
                interval_ms, callback,
                repeat=True, interval_ms=interval_ms,
            )
            self._timers[entry.id] = timer_id
            self._entries[timer_id] = {"entry": entry, "instance": entry.instance}

        elif trigger_type == "cron":
            cron_expr = trigger.get("cron")
            if not cron_expr:
                raise ValueError("cron trigger requires a 'cron' expression")
            try:
                croniter(cron_expr)
            except (ValueError, KeyError) as exc:
                raise ValueError(f"Invalid cron expression: {cron_expr}") from exc
            count = trigger.get("count", -1)
            fired = [0]

            def callback():
                fired[0] += 1
                entry.callback(entry.instance)
                if count > 0 and fired[0] >= count:
                    tid = self._timers.get(entry.id)
                    if tid is not None:
                        self._scheduler.cancel(tid)
                        self._timers.pop(entry.id, None)
                        self._entries.pop(tid, None)

            timer_id = self._scheduler.schedule_cron(
                cron_expr,
                callback,
                count=-1,
            )
            self._timers[entry.id] = timer_id
            self._entries[timer_id] = {"entry": entry, "instance": entry.instance}

    def on_unregistered(self, entry):
        timer_id = self._timers.pop(entry.id, None)
        if timer_id is not None:
            self._scheduler.cancel(timer_id)
            self._entries.pop(timer_id, None)

    def on_instance_removed(self, instance):
        to_remove = [
            eid for eid, tid in list(self._timers.items())
            if self._entries.get(tid, {}).get("instance") is instance
        ]
        for eid in to_remove:
            self.on_unregistered(type("E", (), {"id": eid})())
