from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


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

    @staticmethod
    def _build_default_clear(trigger_cfg):
        if trigger_cfg.get("type") == "condition" and "condition" in trigger_cfg:
            return {"type": "condition", "condition": f"not ({trigger_cfg['condition']})"}
        return None

    def register_instance_alarms(self, instance, alarm_configs):
        for alarm_id, config in alarm_configs.items():
            trigger_cfg = config["trigger"]
            clear_cfg = config.get("clear") if "clear" in config else self._build_default_clear(trigger_cfg)

            trigger_callback = lambda inst, alarm_id=alarm_id, cfg=config: self._on_trigger(inst, alarm_id, cfg)
            trigger_tag = f"alarm:{alarm_id}:trigger"
            trigger_id = self._trigger_registry.register(instance, trigger_cfg, trigger_callback, tag=trigger_tag)

            trigger_ids = [trigger_id]
            if clear_cfg:
                clear_callback = lambda inst, alarm_id=alarm_id, cfg=config: self._on_clear(inst, alarm_id, cfg)
                clear_tag = f"alarm:{alarm_id}:clear"
                clear_id = self._trigger_registry.register(instance, clear_cfg, clear_callback, tag=clear_tag)
                trigger_ids.append(clear_id)

            key = self._key(instance, alarm_id)
            self._trigger_ids[key] = trigger_ids

    def _on_trigger(self, instance, alarm_id: str, config: dict) -> None:
        state = self._get_state(instance, alarm_id)
        if state.state == "active":
            if self._is_in_silence(state):
                return
            state.trigger_count += 1
            state.triggered_at = self._now()
        else:
            state.state = "active"
            state.triggered_at = self._now()
            state.trigger_count = 1
            state.cleared_at = None

        silence_seconds = config.get("silenceInterval", 0)
        if silence_seconds > 0:
            state.silence_expires_at = self._now_offset(silence_seconds)

    def _on_clear(self, instance, alarm_id: str, config: dict) -> None:
        state = self._get_state(instance, alarm_id)
        if state.state != "active":
            return
        state.state = "inactive"
        state.cleared_at = self._now()
        state.silence_expires_at = None

    def _is_in_silence(self, state: AlarmState) -> bool:
        if state.silence_expires_at is None:
            return False
        expires = datetime.fromisoformat(state.silence_expires_at)
        return datetime.now(timezone.utc) < expires

    @staticmethod
    def _now_offset(seconds: int) -> str:
        return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    def unregister_instance_alarms(self, instance):
        keys_to_remove = []
        for key, trigger_ids in self._trigger_ids.items():
            world_id, instance_id, alarm_id = key
            if world_id == instance.world_id and instance_id == instance.instance_id:
                for tid in trigger_ids:
                    self._trigger_registry.unregister(tid)
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del self._trigger_ids[key]
            if key in self._states:
                del self._states[key]
