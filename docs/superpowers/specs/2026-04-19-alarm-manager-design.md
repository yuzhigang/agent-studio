# AlarmManager Design

## Overview

Alarms are a first-class concept in the Agent Studio runtime: each alarm has its own lifecycle (`inactive` → `active` → `inactive`), silence-interval de-duplication, and alarm-specific metadata (`severity`, `level`, `triggerMessage`, `clearMessage`).

This design keeps `alarms` as an independent configuration section (not folded into `behaviors`), while reusing the unified trigger framework (`TriggerRegistry`) for both `trigger` and `clear` evaluation.

## Goals

1. `alarms.trigger` and `alarms.clear` share the **exact same syntax and type space** as `behaviors.trigger` (event, valueChanged, condition, delay, interval, cron).
2. `clear` is optional. For `condition` triggers, a sensible default (`not (trigger condition)`) is generated automatically; for other trigger types, no default clear exists.
3. `silenceInterval` is an alarm-level concept, not a trigger-level concept.
4. No backward compatibility concerns — this is a green-field addition.

## Alarm Lifecycle

```
       ┌─────────────────────────────────────┐
       │                                     │
       ▼                                     │
  ┌─────────┐  trigger fires   ┌────────┐   │
  │inactive │ ────────────────▶│ active │───┘
  └─────────┘                  └────────┘
                                     │
                                     │ clear fires
                                     ▼
                               ┌──────────┐
                               │ inactive │
                               └──────────┘
```

- **Trigger fires** while `inactive` → transition to `active`, execute `onTrigger`.
- **Trigger fires** while `active`:
  - If inside `silenceInterval` → ignored (no re-notification).
  - If `silenceInterval` has expired → re-notification, reset silence timer.
- **Clear fires** while `active` → transition to `inactive`, execute `onClear`.

## Configuration Schema

```yaml
alarms:
  temperatureHigh.warning:
    category: temperatureHigh
    title: 温度过高预警
    severity: warning          # critical | warning | info
    level: 1
    silenceInterval: 300       # seconds, optional, default 0
    triggerMessage: "温度 {temperature}℃ 超过阈值"
    clearMessage: "温度已恢复正常"
    trigger:
      type: condition
      condition: "this.variables.temperature >= this.attributes.threshold"
    clear:                     # optional
      type: condition
      condition: "this.variables.temperature < this.attributes.threshold * 0.8"
```

### Field Reference

| Field | Required | Description |
|-------|----------|-------------|
| `category` | yes | Alarm category, used for grouping/filtering |
| `title` | yes | Human-readable title |
| `severity` | yes | `critical`, `warning`, or `info` |
| `level` | no | Numeric severity level (default 1) |
| `silenceInterval` | no | Seconds to suppress re-notification while alarm is active (default 0) |
| `triggerMessage` | no | Message template when alarm triggers. Supports `this.*` variable interpolation |
| `clearMessage` | no | Message template when alarm clears |
| `trigger` | yes | Trigger configuration; same schema as `behaviors.trigger` |
| `clear` | no | Clear condition; same schema as `behaviors.trigger`. See default-clear rules below |

## Default Clear Behavior

| Trigger Type | Default Clear (when `clear` omitted) |
|-------------|-----------------------------------|
| `condition` | `{"type": "condition", "condition": "not (<trigger condition>)"}` |
| `event` | None — alarm never auto-clears |
| `valueChanged` | None — alarm never auto-clears |
| `delay` / `interval` / `cron` | None — time-based triggers are transient |

**Rationale:**
- Condition triggers monitor a continuous predicate; when the predicate becomes false the alarm should naturally clear.
- Event / valueChanged triggers represent discrete occurrences; there is no natural "opposite" event, so manual clearance is the sensible default.

## AlarmManager Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     AlarmManager                              │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────────┐                     │
│  │ AlarmState   │  │ SilenceTimers    │                     │
│  │ (per alarm)  │  │ (per active alarm)                   │
│  └──────────────┘  └──────────────────┘                     │
│           │                        │                        │
│           └────────────┬───────────┘                        │
│                        ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  TriggerRegistry.register() / .unregister()             ││
│  │  · registers trigger callback → _on_trigger()           ││
│  │  · registers clear callback  → _on_clear()              ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### AlarmState

```python
@dataclass
class AlarmState:
    alarm_id: str
    instance_id: str
    world_id: str
    state: str                 # "inactive" | "active"
    triggered_at: str | None   # ISO timestamp
    cleared_at: str | None     # ISO timestamp
    trigger_count: int         # number of trigger notifications in current active cycle
    silence_expires_at: str | None
```

### SilenceInterval Mechanism

```python
def _on_trigger(self, instance, alarm_id: str, config: dict) -> None:
    state = self._get_state(instance, alarm_id)

    if state.state == "active":
        if self._is_in_silence(state):
            return  # silently ignore
        # silence expired — repeated notification
        state.trigger_count += 1
        self._notify(state, config, repeated=True)
        self._start_silence(instance, alarm_id, config.get("silenceInterval", 0))
        return

    # inactive → active
    state.state = "active"
    state.triggered_at = _now()
    state.trigger_count = 1
    self._notify(state, config, repeated=False)
    self._start_silence(instance, alarm_id, config.get("silenceInterval", 0))
```

### On-Clear Flow

```python
def _on_clear(self, instance, alarm_id: str, config: dict) -> None:
    state = self._get_state(instance, alarm_id)
    if state.state != "active":
        return  # silent skip: already inactive
    state.state = "inactive"
    state.cleared_at = _now()
    state.silence_expires_at = None
    self._notify_clear(state, config)
```

## Runtime Integration

### WorldRegistry

`WorldRegistry.load_world()` creates `AlarmManager` after `TriggerRegistry` is available:

```python
trigger_registry = TriggerRegistry()
# ... add EventTrigger, ValueChangedTrigger, ConditionTrigger, TimerTrigger ...

alarm_manager = AlarmManager(trigger_registry, event_bus, instance_store)

# After instance is created/loaded:
alarm_configs = instance.model.get("alarms", {})
if alarm_configs:
    alarm_manager.register_instance_alarms(instance, alarm_configs)
```

### InstanceManager Hooks

- `create()` — after instance creation, register alarms
- `get()` — after loading from store, register alarms
- `remove()` — before removal, unregister alarms
- `transition_lifecycle(archived)` — before archival, unregister alarms

### Alarm Notification Output

When an alarm triggers or clears, `AlarmManager`:

1. Persists an alarm record to `instance_store` (or a dedicated alarm store).
2. Publishes an event on the event bus:
   - `alarmTriggered` — when alarm becomes active
   - `alarmCleared` — when alarm becomes inactive
3. The event payload contains: `alarmId`, `category`, `severity`, `level`, `message`, `instanceId`, `worldId`, `timestamp`, `triggerCount` (for repeats).

## Message Template Interpolation

`triggerMessage` and `clearMessage` support interpolating instance properties using `{propertyName}` syntax. The interpolation context is built from:

- `this.variables.*`
- `this.attributes.*`
- `this.state.*`

Example:
```yaml
triggerMessage: "温度 {temperature}℃ 超过阈值 {threshold}℃"
```

Interpolation runs at notification time against the current instance state.

## Example: Heartbeat Model with Alarms

```yaml
alarms:
  overheat.warning:
    category: overheat
    title: 传感器温度过高
    severity: warning
    level: 1
    silenceInterval: 60
    triggerMessage: "温度 {temperature}℃ 超过阈值 {threshold}℃"
    clearMessage: "温度已恢复正常"
    trigger:
      type: condition
      condition: "this.variables.temperature >= this.attributes.threshold"
    # clear omitted — defaults to "not (condition)"
```

## Backwards Compatibility

Not applicable. This is a new subsystem added to the runtime. Existing models without `alarms` continue to work unchanged.
