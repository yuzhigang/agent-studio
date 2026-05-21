import asyncio
import random
from src.simulator.config import SourceConfig, _parse_duration
from src.simulator.scripting import SimContext, Event, run_script
from src.simulator.poster import HttpPoster


class SimSource:
    def __init__(self, config: SourceConfig, poster: HttpPoster):
        self._config = config
        self._poster = poster
        self._ctx = SimContext()
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
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

    async def _run(self) -> None:
        tasks = [
            asyncio.create_task(self._run_item(item))
            for item in self._config.schedule
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_item(self, item) -> None:
        while not self._stop_event.is_set():
            interval = _parse_duration(item.every)
            jitter = _parse_duration(item.jitter)
            delay = interval + random.uniform(-jitter, jitter)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=max(0, delay))
            except asyncio.TimeoutError:
                pass
            if self._stop_event.is_set():
                return

            event = self._generate_event(item)
            if event is not None:
                await self._poster.send(self._config.target_world, event)

    def _generate_event(self, schedule_item) -> Event | None:
        if self._config.script:
            func_name = f"on_{schedule_item.event}"
            return run_script(self._config.script, func_name, self._ctx)

        payload = {}
        for key, spec in schedule_item.payload.items():
            if isinstance(spec, dict):
                typ = spec.get("type")
                if typ == "gaussian":
                    payload[key] = self._ctx.gaussian(spec["mean"], spec["std"])
                elif typ == "uniform":
                    payload[key] = self._ctx.uniform(spec["min"], spec["max"])
                elif typ == "exponential":
                    payload[key] = self._ctx.exponential(spec["rate"])
                elif typ == "triangular":
                    payload[key] = self._ctx.triangular(spec["low"], spec["high"], spec["mode"])
                elif typ == "lognormal":
                    payload[key] = self._ctx.lognormal(spec["mu"], spec["sigma"])
                elif typ == "pareto":
                    payload[key] = self._ctx.pareto(spec["alpha"])
                elif typ == "weibull":
                    payload[key] = self._ctx.weibull(spec["alpha"], spec["beta"])
                else:
                    payload[key] = spec.get("value")
            else:
                payload[key] = spec

        return Event(schedule_item.event, payload)
