from abc import ABC, abstractmethod


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


class WorldMessageStore(ABC):
    @abstractmethod
    def inbox_enqueue(
        self,
        world_id: str,
        event_type: str,
        payload: dict,
        source: str,
        scope: str,
        target: str | None,
    ) -> int:
        """Append an incoming message to the world inbox. Returns message id."""
        ...

    @abstractmethod
    def inbox_mark_processed(self, world_id: str, message_id: int) -> None:
        """Mark an inbox message as processed."""
        ...

    @abstractmethod
    def inbox_read_pending(self, world_id: str, limit: int) -> list[dict]:
        """Read unprocessed inbox messages for a world."""
        ...

    @abstractmethod
    def outbox_enqueue(
        self,
        world_id: str,
        event_type: str,
        payload: dict,
        source: str,
        scope: str,
        target: str | None,
    ) -> int:
        """Append an outgoing message to the world outbox. Returns message id."""
        ...

    @abstractmethod
    def outbox_mark_sent(self, world_id: str, message_id: int) -> None:
        """Mark an outbox message as sent."""
        ...

    @abstractmethod
    def outbox_read_pending(self, world_id: str, limit: int) -> list[dict]:
        """Read unsent outbox messages for a world."""
        ...

    @abstractmethod
    def outbox_update_error(
        self,
        world_id: str,
        message_id: int,
        error_count: int,
        retry_after: str | None,
        last_error: str | None,
    ) -> None:
        """Update error metadata for an outbox message."""
        ...


class MessageStore(ABC):
    @abstractmethod
    def inbox_enqueue(
        self,
        event_type: str,
        payload: dict,
        source: str,
        scope: str,
        target: str | None,
    ) -> int:
        """Append an incoming message to the inbox. Returns message id."""
        ...

    @abstractmethod
    def inbox_mark_processed(self, message_id: int) -> None:
        """Mark an inbox message as processed."""
        ...

    @abstractmethod
    def inbox_read_pending(self, limit: int) -> list[dict]:
        """Read unprocessed inbox messages."""
        ...

    @abstractmethod
    def outbox_enqueue(
        self,
        event_type: str,
        payload: dict,
        source: str,
        scope: str,
        target: str | None,
    ) -> int:
        """Append an outgoing message to the outbox. Returns message id."""
        ...

    @abstractmethod
    def outbox_mark_sent(self, message_id: int) -> None:
        """Mark an outbox message as sent."""
        ...

    @abstractmethod
    def outbox_read_pending(self, limit: int) -> list[dict]:
        """Read unsent outbox messages."""
        ...

    @abstractmethod
    def outbox_update_error(
        self,
        message_id: int,
        error_count: int,
        retry_after: str | None,
        last_error: str | None,
    ) -> None:
        """Update error metadata for an outbox message."""
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
