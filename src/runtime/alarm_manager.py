from dataclasses import dataclass, field


@dataclass
class AlarmState:
    alarm_id: str
    instance_id: str
    world_id: str
    state: str = field(default="inactive")
    triggered_at: str | None = field(default=None)
    cleared_at: str | None = field(default=None)
    trigger_count: int = field(default=0)
    silence_expires_at: str | None = field(default=None)


class AlarmManager:
    def __init__(self, trigger_registry, event_bus, store=None):
        self._trigger_registry = trigger_registry
        self._event_bus = event_bus
        self._store = store
        self._states: dict[tuple[str, str, str], AlarmState] = {}
        self._trigger_ids: dict[tuple[str, str, str], list[str]] = {}

    def _key(self, instance, alarm_id: str):
        return (instance.world_id, instance.instance_id, alarm_id)

    def _get_state(self, instance, alarm_id: str) -> AlarmState:
        key = self._key(instance, alarm_id)
        if key not in self._states:
            self._states[key] = AlarmState(
                alarm_id=alarm_id,
                instance_id=instance.instance_id,
                world_id=instance.world_id,
            )
        return self._states[key]
