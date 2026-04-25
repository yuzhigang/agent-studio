from abc import ABC, abstractmethod

from src.runtime.messaging.store import MessageStore


class WorldStore(ABC):
    @abstractmethod
    def save_world(self, world_id: str, config: dict) -> None:
        """Persist world metadata and global configuration."""
        ...

    @abstractmethod
    def load_world(self, world_id: str) -> dict | None:
        """Load world metadata and global configuration."""
        ...

    @abstractmethod
    def delete_world(self, world_id: str) -> bool:
        """Delete world record."""
        ...


class SceneStore(ABC):
    @abstractmethod
    def save_scene(self, world_id: str, scene_id: str, scene_data: dict) -> None:
        """Persist scene metadata."""
        ...

    @abstractmethod
    def load_scene(self, world_id: str, scene_id: str) -> dict | None:
        """Load scene metadata."""
        ...

    @abstractmethod
    def list_scenes(self, world_id: str) -> list[dict]:
        """List all scenes belonging to a world."""
        ...

    @abstractmethod
    def delete_scene(self, world_id: str, scene_id: str) -> bool:
        """Delete scene record."""
        ...


class InstanceStore(ABC):
    @abstractmethod
    def save_instance(self, world_id: str, instance_id: str, scope: str, snapshot: dict) -> None:
        """Persist an instance snapshot."""
        ...

    @abstractmethod
    def load_instance(self, world_id: str, instance_id: str, scope: str) -> dict | None:
        """Load an instance snapshot."""
        ...

    @abstractmethod
    def list_instances(
        self, world_id: str, scope: str | None = None, lifecycle_state: str | None = None
    ) -> list[dict]:
        """List instance snapshots for a world, optionally filtered by scope and lifecycle_state."""
        ...

    @abstractmethod
    def delete_instance(self, world_id: str, instance_id: str, scope: str) -> bool:
        """Delete an instance snapshot."""
        ...


class EventLogStore(ABC):
    @abstractmethod
    def append(
        self,
        world_id: str,
        event_id: str,
        event_type: str,
        payload: dict,
        source: str,
        scope: str,
    ) -> None:
        """Append an event to the world event log."""
        ...

    @abstractmethod
    def replay_after(self, world_id: str, last_event_id: str | None) -> list[dict]:
        """Replay all events after the given event_id.

        If last_event_id is None, returns all events.
        If last_event_id is not None and does not exist, raises ValueError.
        """
        ...

class AlarmStore(ABC):
    @abstractmethod
    def save_alarm(self, world_id: str, alarm_data: dict) -> None:
        """Upsert an alarm record."""
        ...

    @abstractmethod
    def load_alarm(self, world_id: str, instance_id: str, alarm_id: str) -> dict | None:
        """Load a single alarm record by composite key."""
        ...

    @abstractmethod
    def list_alarms(
        self,
        world_id: str,
        instance_id: str | None = None,
        state: str | None = None,
        triggered_after: str | None = None,
        triggered_before: str | None = None,
    ) -> list[dict]:
        """List alarms with optional filters."""
        ...

    @abstractmethod
    def delete_alarm(self, world_id: str, instance_id: str, alarm_id: str) -> bool:
        """Delete an alarm record."""
        ...

    @abstractmethod
    def clear_alarm(self, world_id: str, instance_id: str, alarm_id: str) -> bool:
        """Manually clear an active alarm. Returns True if cleared."""
        ...
