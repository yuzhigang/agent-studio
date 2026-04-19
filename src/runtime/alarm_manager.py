import re
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

    def _interpolate_message(self, template: str, instance) -> str:
        def replacer(match: re.Match) -> str:
            key = match.group(1)
            for source in (instance.variables, instance.attributes, instance.state):
                if key in source:
                    return str(source[key])
            return match.group(0)

        return re.sub(r"\{(\w+)\}", replacer, template)

    def _notify_trigger(self, state: AlarmState, config: dict, instance, repeated: bool = False) -> None:
        message = self._interpolate_message(config.get("triggerMessage", ""), instance)
        payload = {
            "alarmId": state.alarm_id,
            "category": config.get("category"),
            "title": config.get("title"),
            "severity": config.get("severity"),
            "level": config.get("level"),
            "message": message,
            "instanceId": instance.instance_id,
            "worldId": instance.world_id,
            "timestamp": state.triggered_at,
            "triggerCount": state.trigger_count,
            "repeated": repeated,
        }
        if self._event_bus is not None:
            self._event_bus.publish("alarmTriggered", payload, source=instance.instance_id, scope="world")

    def _notify_clear(self, state: AlarmState, config: dict, instance) -> None:
        message = self._interpolate_message(config.get("clearMessage", ""), instance)
        payload = {
            "alarmId": state.alarm_id,
            "category": config.get("category"),
            "title": config.get("title"),
            "severity": config.get("severity"),
            "level": config.get("level"),
            "message": message,
            "instanceId": instance.instance_id,
            "worldId": instance.world_id,
            "timestamp": state.cleared_at,
        }
        if self._event_bus is not None:
            self._event_bus.publish("alarmCleared", payload, source=instance.instance_id, scope="world")

    def _on_trigger(self, instance, alarm_id: str, config: dict) -> None:
        state = self._get_state(instance, alarm_id)
        if state.state == "active":
            if self._is_in_silence(state):
                return
            state.trigger_count += 1
            state.triggered_at = self._now()
            self._notify_trigger(state, config, instance, repeated=True)
        else:
            state.state = "active"
            state.triggered_at = self._now()
            state.trigger_count = 1
            state.cleared_at = None
            self._notify_trigger(state, config, instance, repeated=False)

        silence_seconds = config.get("silenceInterval", 0)
        if silence_seconds > 0:
            state.silence_expires_at = self._now_offset(silence_seconds)

        self._persist_alarm_state(instance, alarm_id, config, is_clear=False)

    def _on_clear(self, instance, alarm_id: str, config: dict) -> None:
        state = self._get_state(instance, alarm_id)
        if state.state != "active":
            return
        state.state = "inactive"
        state.cleared_at = self._now()
        state.silence_expires_at = None
        self._notify_clear(state, config, instance)
        self._persist_alarm_state(instance, alarm_id, config, is_clear=True)

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

    def _persist_alarm_state(self, instance, alarm_id: str, config: dict, is_clear: bool = False) -> None:
        if self._store is None:
            return
        state = self._get_state(instance, alarm_id)
        payload = self._extract_payload(config.get("triggerMessage", ""), instance)
        alarm_data = {
            "instance_id": instance.instance_id,
            "alarm_id": alarm_id,
            "category": config.get("category"),
            "severity": config.get("severity"),
            "level": config.get("level"),
            "state": state.state,
            "trigger_count": state.trigger_count,
            "trigger_message": self._interpolate_message(config.get("triggerMessage", ""), instance) or None,
            "clear_message": self._interpolate_message(config.get("clearMessage", ""), instance) or None,
            "triggered_at": state.triggered_at,
            "cleared_at": state.cleared_at,
            "payload": payload if payload else None,
        }
        self._store.save_alarm(instance.world_id, alarm_data)

    def _extract_payload(self, template: str, instance) -> dict:
        import re
        keys = set(re.findall(r"\{(\w+)\}", template))
        payload = {}
        for key in keys:
            for source in (instance.variables, instance.attributes, instance.state):
                if key in source:
                    payload[key] = source[key]
                    break
        return payload

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
