import threading

from src.runtime.trigger_registry import Trigger


class TimerScheduler:
    def __init__(self):
        self._timers = {}  # timer_id -> threading.Timer
        self._counter = 0

    def schedule(self, delay_ms, callback, repeat=False, interval_ms=None):
        self._counter += 1
        timer_id = f"timer_{self._counter}"

        def wrapper():
            callback()
            if repeat and timer_id in self._timers:
                self._schedule_next(timer_id, interval_ms, callback, True, interval_ms)

        timer = threading.Timer(delay_ms / 1000.0, wrapper)
        self._timers[timer_id] = timer
        timer.start()
        return timer_id

    def _schedule_next(self, timer_id, delay_ms, callback, repeat, interval_ms):
        timer = threading.Timer(delay_ms / 1000.0, lambda: self._run_and_reschedule(timer_id, callback, repeat, interval_ms))
        self._timers[timer_id] = timer
        timer.start()

    def _run_and_reschedule(self, timer_id, callback, repeat, interval_ms):
        if timer_id not in self._timers:
            return
        callback()
        if repeat and timer_id in self._timers:
            self._schedule_next(timer_id, interval_ms, callback, True, interval_ms)

    def cancel(self, timer_id):
        timer = self._timers.pop(timer_id, None)
        if timer:
            timer.cancel()

    def cancel_all_for_instance(self, instance):
        to_cancel = [tid for tid, info in getattr(self, '_entries', {}).items()
                     if info.get('instance') is instance]
        for tid in to_cancel:
            self.cancel(tid)


class TimerTrigger(Trigger):
    trigger_types = {"delay", "interval", "cron"}

    def __init__(self, scheduler=None):
        self._scheduler = scheduler or TimerScheduler()
        self._timers = {}  # entry.id -> timer_id
        self._entries = {}  # timer_id -> {"entry": entry, "instance": instance}

    def on_registered(self, entry):
        trigger = entry.trigger
        trigger_type = trigger["type"]

        if trigger_type == "delay":
            delay_ms = trigger.get("delay", 0)
            timer_id = self._scheduler.schedule(delay_ms, lambda: entry.callback(entry.instance))
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
                    if tid:
                        self._scheduler.cancel(tid)
                        self._timers.pop(entry.id, None)
                        self._entries.pop(tid, None)

            timer_id = self._scheduler.schedule(interval_ms, callback, repeat=True, interval_ms=interval_ms)
            self._timers[entry.id] = timer_id
            self._entries[timer_id] = {"entry": entry, "instance": entry.instance}

        elif trigger_type == "cron":
            # Deferred: cron support requires croniter. For now, register but don't schedule.
            pass

    def on_unregistered(self, entry):
        timer_id = self._timers.pop(entry.id, None)
        if timer_id:
            self._scheduler.cancel(timer_id)
            self._entries.pop(timer_id, None)

    def on_instance_removed(self, instance):
        to_remove = [eid for eid, tid in list(self._timers.items())
                     if self._entries.get(tid, {}).get("instance") is instance]
        for eid in to_remove:
            self.on_unregistered(type("E", (), {"id": eid})())
