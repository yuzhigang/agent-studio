import asyncio
import unittest.mock as mock
from datetime import datetime, timedelta

import pytest
from src.runtime.triggers.timer_trigger import TimerTrigger, TimerScheduler
from src.runtime.trigger_registry import TriggerEntry


@pytest.mark.anyio
async def test_delay_trigger_fires_after_delay():
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

    await asyncio.sleep(0.15)
    assert len(calls) == 1
    assert calls[0] is inst


@pytest.mark.anyio
async def test_interval_trigger_fires_multiple_times():
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

    await asyncio.sleep(0.25)
    assert len(calls) == 3


@pytest.mark.anyio
async def test_interval_infinite_count():
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

    await asyncio.sleep(0.13)
    assert len(calls) == 2

    tt.on_unregistered(entry)
    await asyncio.sleep(0.1)
    assert len(calls) == 2


@pytest.mark.anyio
async def test_timer_unregistered_cancels():
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

    await asyncio.sleep(0.1)
    assert len(calls) == 0


@pytest.mark.anyio
async def test_instance_removed_cancels_all():
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

    await asyncio.sleep(0.1)
    assert len(calls) == 0


@pytest.mark.anyio
async def test_cron_trigger_fires_at_next_tick():
    scheduler = TimerScheduler()
    tt = TimerTrigger(scheduler)

    calls = []
    inst = object()
    entry = TriggerEntry(
        inst,
        {"type": "cron", "name": "tick", "cron": "*/1 * * * *"},
        lambda i: calls.append(i),
        "b1",
    )

    # Patch croniter so the "next" time is 50ms away deterministically
    fake_now = datetime(2024, 1, 1, 0, 0, 0)
    with mock.patch("src.runtime.triggers.timer_trigger.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)

        with mock.patch("src.runtime.triggers.timer_trigger.croniter") as mock_cron:
            mock_iter = mock_cron.return_value
            # First call: next tick 50ms away
            mock_iter.get_next.side_effect = [
                fake_now + timedelta(seconds=0.05),
                fake_now + timedelta(seconds=0.10),
            ]

            tt.on_registered(entry)
            await asyncio.sleep(0.08)
            assert len(calls) == 1
            await asyncio.sleep(0.1)
            assert len(calls) == 2

    tt.on_unregistered(entry)
