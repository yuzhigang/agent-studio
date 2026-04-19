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
