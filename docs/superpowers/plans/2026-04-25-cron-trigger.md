# cron Trigger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `cron` trigger type in `TimerTrigger` / `TimerScheduler`, using `croniter` for expression parsing and asyncio for scheduling.

**Architecture:** Extend `TimerScheduler` with `schedule_cron()` that loops — compute next time with `croniter`, `asyncio.sleep`, fire callback, repeat. `TimerTrigger.on_registered` wires `cron` entries to `schedule_cron` using the same `entry.id -> timer_id` mapping as `delay`/`interval`.

**Tech Stack:** Python 3.12+, asyncio, croniter, pytest-anyio

---

## File Map

| File | Action | Responsibility |
|------|--------|--------------|
| `pyproject.toml` | Modify | Add `croniter>=2.0` to project dependencies |
| `src/runtime/triggers/timer_trigger.py` | Modify | Add `schedule_cron` to `TimerScheduler`; fill `cron` branch in `TimerTrigger.on_registered` |
| `tests/runtime/test_timer_trigger.py` | Modify | Add cron-specific tests |

---

### Task 1: Add `croniter` dependency

**Files:**
- Modify: `pyproject.toml:10-16`

- [ ] **Step 1: Add dependency**

Insert `"croniter>=2.0",` into the `dependencies` list (alphabetical order is not required, but keep it tidy):

```toml
dependencies = [
    "watchdog>=3.0.0",
    "pyyaml>=6.0",
    "fasteners>=0.19",
    "websockets>=12.0",
    "aiohttp>=3.9",
    "croniter>=2.0",
]
```

- [ ] **Step 2: Install locally**

```bash
pip install croniter>=2.0
```

Run: `python -c "import croniter; print(croniter.__version__)"`
Expected: version string printed, no import error.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "deps: add croniter for cron trigger support"
```

---

### Task 2: Implement `schedule_cron` and `TimerTrigger.cron` branch

**Files:**
- Modify: `src/runtime/triggers/timer_trigger.py`

- [ ] **Step 1: Write the failing cron test (to drive implementation)**

Append to `tests/runtime/test_timer_trigger.py`:

```python
import unittest.mock as mock
from datetime import datetime, timedelta


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
                fake_now + timedelta(seconds=0.15),
            ]

            tt.on_registered(entry)
            await asyncio.sleep(0.08)
            assert len(calls) == 1
            await asyncio.sleep(0.1)
            assert len(calls) == 2

    tt.on_unregistered(entry)
```

Run: `pytest tests/runtime/test_timer_trigger.py::test_cron_trigger_fires_at_next_tick -v`
Expected: FAIL with `NameError: name 'croniter' is not defined` or `TimerTrigger.on_registered` `cron` branch not calling `schedule_cron`.

- [ ] **Step 2: Implement `schedule_cron` in `TimerScheduler`**

Modify `src/runtime/triggers/timer_trigger.py`. Add `from datetime import datetime` and `from croniter import croniter` at the top, then add the new method to `TimerScheduler`:

```python
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
        # ... existing code unchanged ...

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
                        # Invalid cron expression — stop the runner
                        break

                    wait_seconds = (next_time - datetime.now()).total_seconds()
                    if wait_seconds > 0:
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
        # ... existing code unchanged ...

    def cancel_all(self) -> None:
        # ... existing code unchanged ...
```

**Note:** Keep the original `schedule` and `cancel` methods exactly as they are — only insert `schedule_cron` between `schedule` and `cancel`.

- [ ] **Step 3: Wire `cron` branch in `TimerTrigger.on_registered`**

Replace the `elif trigger_type == "cron"` block in `TimerTrigger.on_registered`:

```python
        elif trigger_type == "cron":
            cron_expr = trigger.get("cron")
            if not cron_expr:
                raise ValueError("cron trigger requires a 'cron' expression")
            count = trigger.get("count", -1)
            timer_id = self._scheduler.schedule_cron(
                cron_expr,
                lambda e=entry: e.callback(e.instance),
                count=count,
            )
            self._timers[entry.id] = timer_id
            self._entries[timer_id] = {"entry": entry, "instance": entry.instance}
```

- [ ] **Step 4: Run the cron test**

Run: `pytest tests/runtime/test_timer_trigger.py::test_cron_trigger_fires_at_next_tick -v`
Expected: PASS

- [ ] **Step 5: Run all timer tests to ensure no regressions**

Run: `pytest tests/runtime/test_timer_trigger.py -v`
Expected: All existing tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add src/runtime/triggers/timer_trigger.py
git commit -m "feat: implement cron trigger in TimerTrigger and TimerScheduler"
```

---

### Task 3: Add remaining cron tests

**Files:**
- Modify: `tests/runtime/test_timer_trigger.py`

- [ ] **Step 1: Write `test_cron_trigger_with_count_stops_after_n`**

Append to `tests/runtime/test_timer_trigger.py`:

```python
@pytest.mark.anyio
async def test_cron_trigger_with_count_stops_after_n():
    scheduler = TimerScheduler()
    tt = TimerTrigger(scheduler)

    calls = []
    inst = object()
    entry = TriggerEntry(
        inst,
        {"type": "cron", "name": "tick", "cron": "*/1 * * * *", "count": 2},
        lambda i: calls.append(i),
        "b1",
    )

    fake_now = datetime(2024, 1, 1, 0, 0, 0)
    with mock.patch("src.runtime.triggers.timer_trigger.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)

        with mock.patch("src.runtime.triggers.timer_trigger.croniter") as mock_cron:
            mock_iter = mock_cron.return_value
            # Provide enough "next" times
            mock_iter.get_next.side_effect = [
                fake_now + timedelta(seconds=0.05),
                fake_now + timedelta(seconds=0.10),
                fake_now + timedelta(seconds=0.15),
            ]

            tt.on_registered(entry)
            await asyncio.sleep(0.20)
            assert len(calls) == 2
            # After count is reached, the timer should have cancelled itself
            assert entry.id not in tt._timers
```

Run: `pytest tests/runtime/test_timer_trigger.py::test_cron_trigger_with_count_stops_after_n -v`
Expected: PASS

- [ ] **Step 2: Write `test_cron_trigger_unregistered_cancels`**

Append:

```python
@pytest.mark.anyio
async def test_cron_trigger_unregistered_cancels():
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

    fake_now = datetime(2024, 1, 1, 0, 0, 0)
    with mock.patch("src.runtime.triggers.timer_trigger.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)

        with mock.patch("src.runtime.triggers.timer_trigger.croniter") as mock_cron:
            mock_iter = mock_cron.return_value
            mock_iter.get_next.return_value = fake_now + timedelta(seconds=0.20)

            tt.on_registered(entry)
            tt.on_unregistered(entry)
            await asyncio.sleep(0.05)
            assert len(calls) == 0
```

Run: `pytest tests/runtime/test_timer_trigger.py::test_cron_trigger_unregistered_cancels -v`
Expected: PASS

- [ ] **Step 3: Write `test_cron_trigger_instance_removed_cancels`**

Append:

```python
@pytest.mark.anyio
async def test_cron_trigger_instance_removed_cancels():
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

    fake_now = datetime(2024, 1, 1, 0, 0, 0)
    with mock.patch("src.runtime.triggers.timer_trigger.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)

        with mock.patch("src.runtime.triggers.timer_trigger.croniter") as mock_cron:
            mock_iter = mock_cron.return_value
            mock_iter.get_next.return_value = fake_now + timedelta(seconds=0.20)

            tt.on_registered(entry)
            tt.on_instance_removed(inst)
            await asyncio.sleep(0.05)
            assert len(calls) == 0
```

Run: `pytest tests/runtime/test_timer_trigger.py::test_cron_trigger_instance_removed_cancels -v`
Expected: PASS

- [ ] **Step 4: Write `test_cron_invalid_expression_raises`**

Append:

```python
def test_cron_invalid_expression_raises():
    scheduler = TimerScheduler()
    tt = TimerTrigger(scheduler)

    inst = object()
    entry = TriggerEntry(
        inst,
        {"type": "cron", "name": "bad", "cron": "not-a-cron"},
        lambda i: None,
        "b1",
    )

    with pytest.raises(ValueError, match="Invalid cron expression"):
        tt.on_registered(entry)
```

Run: `pytest tests/runtime/test_timer_trigger.py::test_cron_invalid_expression_raises -v`
Expected: PASS

- [ ] **Step 5: Run full timer trigger test suite**

Run: `pytest tests/runtime/test_timer_trigger.py -v`
Expected: All 10 tests PASS (5 existing + 5 new).

- [ ] **Step 6: Commit**

```bash
git add tests/runtime/test_timer_trigger.py
git commit -m "test: add cron trigger coverage"
```

---

### Task 4: Add `cron` branch validation in `TimerTrigger.on_registered` for missing expression

**Files:**
- Modify: `src/runtime/triggers/timer_trigger.py`

- [ ] **Step 1: Verify the missing-expression check**

In Task 2 we already added:

```python
            cron_expr = trigger.get("cron")
            if not cron_expr:
                raise ValueError("cron trigger requires a 'cron' expression")
```

If this was not included, add it now. Then run the invalid-expression test again:

Run: `pytest tests/runtime/test_timer_trigger.py::test_cron_invalid_expression_raises -v`
Expected: PASS

- [ ] **Step 2: Commit (if any additional change)**

```bash
git add src/runtime/triggers/timer_trigger.py
git commit -m "feat: validate cron expression presence in TimerTrigger"
```

---

## Self-Review

### 1. Spec coverage

| Spec Requirement | Task |
|---|---|
| `schedule_cron` in `TimerScheduler` | Task 2, Step 2 |
| `cron` branch wired in `TimerTrigger.on_registered` | Task 2, Step 3 |
| `count` support | Task 2, Step 2 (`count` param + fired tracking) |
| Local time (datetime.now) | Task 2, Step 2 (`datetime.now()` in loop) |
| Invalid cron expression → ValueError | Task 2, Step 3 + Task 4 |
| callback exception swallowed | Task 2, Step 2 (`except Exception: pass`) |
| cancel races handled | Task 2, Step 2 (checks `timer_id in self._tasks` before and after sleep) |
| `croniter` dependency added | Task 1 |
| Tests: fires, count, unregister, instance_removed, invalid | Task 3 |

No gaps.

### 2. Placeholder scan

- No "TBD", "TODO", "implement later" found.
- All test code is explicit with complete assertions.
- All implementation code is complete.
- No "similar to Task N" shortcuts.

### 3. Type consistency

- `schedule_cron(self, cron_expr: str, callback, *, count: int = -1) -> str` — matches `schedule` signature style.
- `TimerTrigger.on_registered` stores `timer_id` in `self._timers[entry.id]` and `self._entries[timer_id]` — same pattern as `delay`/`interval`.
- `on_unregistered` / `on_instance_removed` unchanged — they already work with these dicts.

All consistent. Plan is ready.
