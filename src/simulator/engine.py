import asyncio
import signal
from src.simulator.config import SimulatorConfig
from src.simulator.scheduler import Scheduler


class EventSimulator:
    def __init__(self, config: SimulatorConfig):
        self._config = config
        self._scheduler = Scheduler(config)
        self._shutdown_event = asyncio.Event()

    async def run(self) -> int:
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._shutdown_event.set)
            except (ValueError, OSError, NotImplementedError):
                pass

        await self._scheduler.start()
        print(f"[simulator] Started {len(self._config.sources)} source(s)")
        print("[simulator] Press Ctrl+C to stop")

        try:
            await self._shutdown_event.wait()
        finally:
            print("[simulator] Shutting down...")
            await self._scheduler.stop()
            print("[simulator] Stopped")
        return 0
