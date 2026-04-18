from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any


class MetricStore(ABC):
    @abstractmethod
    def write(
        self,
        world_id: str,
        instance_id: str,
        variable: str,
        value: Any,
        timestamp: datetime,
    ) -> None:
        """Write a metric value for an instance variable at a given timestamp."""
        ...

    @abstractmethod
    def latest(self, world_id: str, instance_id: str, variable: str) -> Any | None:
        """Return the latest metric value for an instance variable, or None."""
        ...


class MemoryMetricStore(MetricStore):
    """In-memory MetricStore implementation for testing."""

    def __init__(self):
        self._data: dict[tuple[str, str, str], list[tuple[datetime, Any]]] = {}

    def write(
        self,
        world_id: str,
        instance_id: str,
        variable: str,
        value: Any,
        timestamp: datetime,
    ) -> None:
        key = (world_id, instance_id, variable)
        self._data.setdefault(key, []).append((timestamp, value))

    def latest(self, world_id: str, instance_id: str, variable: str) -> Any | None:
        key = (world_id, instance_id, variable)
        entries = self._data.get(key, [])
        if not entries:
            return None
        entries.sort(key=lambda x: x[0])
        return entries[-1][1]
