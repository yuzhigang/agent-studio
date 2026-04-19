import pytest
import time
from src.runtime.triggers.timer_trigger import TimerTrigger, TimerScheduler
from src.runtime.trigger_registry import TriggerEntry


def test_delay_trigger_fires_after_delay():
    scheduler = TimerScheduler()
    tt = TimerTrigger(scheduler)

    calls = []
    inst = object()
    entry = TriggerEntry(
        inst,
        {"type": "delay", "name": "alert", "delay": 50},
        lambda i: calls.append(i),
        "b1",
    )
    tt.on_registered(entry)

    time.sleep(0.15)  # wait for 50ms delay + margin
    assert len(calls) == 1
    assert calls[0] is inst


def test_interval_trigger_fires_multiple_times():
    scheduler = TimerScheduler()
    tt = TimerTrigger(scheduler)

    calls = []
    inst = object()
    entry = TriggerEntry(
        inst,
        {"type": "interval", "name": "heartbeat", "interval": 50, "count": 3},
        lambda i: calls.append(i),
        "b1",
    )
    tt.on_registered(entry)

    time.sleep(0.25)  # wait for 3 intervals + margin
    assert len(calls) == 3


def test_interval_infinite_count():
    scheduler = TimerScheduler()
    tt = TimerTrigger(scheduler)

    calls = []
    inst = object()
    entry = TriggerEntry(
        inst,
        {"type": "interval", "name": "heartbeat", "interval": 50, "count": -1},
        lambda i: calls.append(i),
        "b1",
    )
    tt.on_registered(entry)

    time.sleep(0.13)  # 2 intervals
    assert len(calls) == 2

    tt.on_unregistered(entry)
    time.sleep(0.1)
    assert len(calls) == 2  # should stop after unregistered


def test_timer_unregistered_cancels():
    scheduler = TimerScheduler()
    tt = TimerTrigger(scheduler)

    calls = []
    inst = object()
    entry = TriggerEntry(
        inst,
        {"type": "delay", "name": "alert", "delay": 200},
        lambda i: calls.append(i),
        "b1",
    )
    tt.on_registered(entry)
    tt.on_unregistered(entry)

    time.sleep(0.1)
    assert len(calls) == 0


def test_instance_removed_cancels_all():
    scheduler = TimerScheduler()
    tt = TimerTrigger(scheduler)

    calls = []
    inst = object()
    entry = TriggerEntry(
        inst,
        {"type": "delay", "name": "alert", "delay": 200},
        lambda i: calls.append(i),
        "b1",
    )
    tt.on_registered(entry)
    tt.on_instance_removed(inst)

    time.sleep(0.1)
    assert len(calls) == 0
