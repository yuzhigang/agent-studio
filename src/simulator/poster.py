import aiohttp
from src.simulator.scripting import Event


class HttpPoster:
    def __init__(self, supervisor_url: str):
        self._base_url = supervisor_url.rstrip("/")
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        self._session = aiohttp.ClientSession()

    async def stop(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def send(self, world_id: str, event: Event) -> bool:
        if self._session is None:
            raise RuntimeError("Poster not started")
        url = f"{self._base_url}/api/worlds/{world_id}/events"
        # Broadcast to world; EventBus routes by event_type subscription
        payload = {
            "event_type": event.event_type,
            "payload": event.payload,
            "scope": event.scope,
            "target": world_id,
        }
        async with self._session.post(url, json=payload) as resp:
            ok = resp.status == 200
            if not ok:
                print(f"[simulator] POST failed: {resp.status} {event.event_type}")
            return ok

    async def send_batch(self, world_id: str, events: list[Event]) -> bool:
        if self._session is None:
            raise RuntimeError("Poster not started")
        url = f"{self._base_url}/api/worlds/{world_id}/events/batch"
        batch = []
        for e in events:
            item = {
                "event_type": e.event_type,
                "payload": e.payload,
                "scope": e.scope,
                "target": world_id,
            }
            batch.append(item)
        async with self._session.post(url, json={"events": batch}) as resp:
            return resp.status == 200
