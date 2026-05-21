from src.simulator.config import SimulatorConfig
from src.simulator.source import SimSource
from src.simulator.poster import HttpPoster


class Scheduler:
    def __init__(self, config: SimulatorConfig):
        self._config = config
        self._poster = HttpPoster(config.supervisor_url)
        self._sources: list[SimSource] = []

    async def start(self) -> None:
        await self._poster.start()
        for src_cfg in self._config.sources:
            source = SimSource(src_cfg, self._poster)
            self._sources.append(source)
            await source.start()

    async def stop(self) -> None:
        for source in self._sources:
            await source.stop()
        self._sources.clear()
        await self._poster.stop()
