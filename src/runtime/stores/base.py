from abc import ABC, abstractmethod


class ProjectStore(ABC):
    @abstractmethod
    def save_project(self, project_id: str, config: dict) -> None:
        """Persist project metadata and global configuration."""
        ...

    @abstractmethod
    def load_project(self, project_id: str) -> dict | None:
        """Load project metadata and global configuration."""
        ...

    @abstractmethod
    def delete_project(self, project_id: str) -> bool:
        """Delete project record."""
        ...


class SceneStore(ABC):
    @abstractmethod
    def save_scene(self, project_id: str, scene_id: str, scene_data: dict) -> None:
        """Persist scene metadata."""
        ...

    @abstractmethod
    def load_scene(self, project_id: str, scene_id: str) -> dict | None:
        """Load scene metadata."""
        ...

    @abstractmethod
    def list_scenes(self, project_id: str) -> list[dict]:
        """List all scenes belonging to a project."""
        ...

    @abstractmethod
    def delete_scene(self, project_id: str, scene_id: str) -> bool:
        """Delete scene record."""
        ...


class InstanceStore(ABC):
    @abstractmethod
    def save_instance(self, project_id: str, instance_id: str, scope: str, snapshot: dict) -> None:
        """Persist an instance snapshot."""
        ...

    @abstractmethod
    def load_instance(self, project_id: str, instance_id: str, scope: str) -> dict | None:
        """Load an instance snapshot."""
        ...

    @abstractmethod
    def list_instances(
        self, project_id: str, scope: str | None = None, lifecycle_state: str | None = None
    ) -> list[dict]:
        """List instance snapshots for a project, optionally filtered by scope and lifecycle_state."""
        ...

    @abstractmethod
    def delete_instance(self, project_id: str, instance_id: str, scope: str) -> bool:
        """Delete an instance snapshot."""
        ...


class EventLogStore(ABC):
    @abstractmethod
    def append(
        self,
        project_id: str,
        event_id: str,
        event_type: str,
        payload: dict,
        source: str,
        scope: str,
    ) -> None:
        """Append an event to the project event log."""
        ...

    @abstractmethod
    def replay_after(self, project_id: str, last_event_id: str | None) -> list[dict]:
        """Replay all events after the given event_id.

        If last_event_id is None, returns all events.
        If last_event_id is not None and does not exist, raises ValueError.
        """
        ...
