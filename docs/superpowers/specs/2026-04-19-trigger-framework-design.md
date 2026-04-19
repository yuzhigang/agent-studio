# Trigger 框架设计

## 背景

当前运行时存在状态机 transitions 不生效的问题：实例状态始终停留在 `idle`，无法通过 `event` 或 `condition` 触发状态迁移。根本原因是 transitions 的 trigger 从未被评估，且 behaviors 的 `stateEnter` 触发也从未被触发（因为状态没变过）。

## 设计目标

1. **统一触发机制** — 所有"触发 → 响应"走同一套框架
2. **概念清晰** — transitions 是状态图定义，behaviors 是触发响应
3. **精确评估** — condition 触发器只在其依赖的数据变更时评估

## 核心洞察

**trigger 是通用框架**，不只用于 transitions，也用于 behaviors。

**transitions 和 behaviors 的关系：**
- `transitions` 定义"状态流转路径"（从哪到哪）
- `behaviors` 定义"触发后做什么"（动作列表）
- transition 只是 behavior action 的一种类型
- 所有触发逻辑统一到 `behaviors`，`transitions` 去 trigger

## 外部触发 3 大来源

| 来源 | 触发时机 | trigger 类型 | 典型场景 |
|---|---|---|---|
| **外部事件** | 事件总线收到事件时 | `event` | 用户指令、实例间消息 |
| **定时器** | 时间到达时 | `delay` / `interval` / `cron` | 心跳、定时任务、定时检查 |
| **数据泵入** | 属性/变量/派生属性值变更时 | `valueChanged` / `condition` | 传感器上报、指标变化、状态变更 |

**属性统一概念：** 当前运行时中 `Instance.attributes`、`Instance.variables` 以及 model 中 `derivedProperties` 统一在 trigger 框架中称为 **property**。触发器中通过路径访问：`attributes.threshold`、`variables.temperature`、`derivedProperties.area`。

## Property 命名约定

**全局唯一：** `variables`、`attributes`、`derivedProperties` 中的命名在全局范围内不允许重名。

```yaml
# 合法
variables:
  temperature: { ... }
attributes:
  threshold: { ... }

# 非法（variables.temperature 和 attributes.temperature 重名）
variables:
  temperature: { ... }
attributes:
  temperature: { ... }  # ERROR: 与 variables.temperature 重名
```

## Trigger 类型（6 种）

| 类型 | 语义 | `name` 含义 | 示例 |
|---|---|---|---|
| `event` | 收到同名事件时触发 | 事件名 | `name: "beat"` |
| `valueChanged` | property 值变为目标值时触发 | 属性路径 | `name: "state.current"`, `value: "monitoring"` |
| `condition` | 条件在窗口内持续满足时触发 | 标签/标识 | `name: "overheatCheck"`, `condition: "temp >= 80"` |
| `delay` | 延时一定时间后一次性触发 | 标签/标识 | `name: "delayedAlert"`, `delay: 5000` |
| `interval` | 周期性触发 | 标签/标识 | `name: "heartbeat"`, `interval: 1000` |
| `cron` | cron 表达式定时触发 | 标签/标识 | `name: "dailyReport"`, `cron: "0 9 * * *"` |

**stateEnter 统一为 `valueChanged`：**
- `stateEnter` → `type: valueChanged, name: "state.current", value: "monitoring"`

## Schema 改造

### transitions 去 trigger

```yaml
transitions:
  startMonitoring:
    from: idle
    to: monitoring
  tempOverThreshold:
    from: monitoring
    to: alert
```

### behaviors 统一所有触发

```yaml
behaviors:
  # 外部事件 → 状态迁移
  onStart:
    trigger:
      type: event
      name: start
    actions:
      - type: transition
        transition: startMonitoring

  # 条件满足 → 状态迁移 + 脚本
  onOverheat:
    trigger:
      type: condition
      name: overheatCheck
      condition: "this.variables.temperature >= this.attributes.threshold"
      window:
        type: time-sliding
        duration: 1
    actions:
      - type: transition
        transition: tempOverThreshold
      - type: runScript
        script: this.variables.alertCount += 1

  # 状态变更 → 执行脚本（原 stateEnter）
  onEnterMonitoring:
    trigger:
      type: valueChanged
      name: state.current
      value: monitoring
    actions:
      - type: runScript
        script: print(">>> 进入监控模式")

  # 变量变化 → 执行脚本
  onTemperatureChange:
    trigger:
      type: valueChanged
      name: variables.temperature
    actions:
      - type: runScript
        script: print(f"温度变化: {this.variables.temperature}")

  # 周期性触发 → 心跳计数
  onHeartbeat:
    trigger:
      type: interval
      name: heartbeat
      interval: 1000
      count: -1
    actions:
      - type: runScript
        script: this.variables.count += 1

  # 延时触发 → 延时告警
  onDelayedAlert:
    trigger:
      type: delay
      name: delayedAlert
      delay: 5000
    actions:
      - type: runScript
        script: print("延时告警触发")

  # cron 触发 → 日报
  onDailyReport:
    trigger:
      type: cron
      name: dailyReport
      cron: "0 9 * * *"
      timezone: "UTC"
    actions:
      - type: runScript
        script: print("每日报告")
```

### trigger 统一配置结构

```yaml
trigger:
  # === 类型（必填）===
  type: event | valueChanged | condition | delay | interval | cron

  # === name（所有类型必填，语义不同）===
  # event: 事件名
  # valueChanged: 属性路径（如 "state.current"、"variables.temperature"）
  # condition: 标签/标识
  # delay: 标签/标识
  # interval: 标签/标识
  # cron: 标签/标识
  name: "..."

  # === 过滤（所有类型可选）===
  when: "..."           # 额外过滤表达式

  # === valueChanged 特有 ===
  value: "..."          # 目标值（选填，不填则任何变化都触发）

  # === condition 特有 ===
  condition: "..."      # 条件表达式
  window:
    type: time-sliding | count-sliding | time-tumbling
    duration: 5          # 秒 或 次数

  # === delay 特有 ===
  delay: 1000           # 延时毫秒数

  # === interval 特有 ===
  interval: 1000        # 周期毫秒数
  count: -1             # 重复次数（-1=无限）

  # === cron 特有 ===
  cron: "0 9 * * *"
  timezone: "UTC"

  # === 执行控制（所有类型共用）===
  executeDelay: 0       # 触发后延迟执行回调（毫秒）
  repeat: false         # condition 类型：false=once, true=continuous
```

## 运行时架构

### 组件关系

```
EventBus.publish("start", ...)
  → EventTrigger (订阅 EventBus)
    → 匹配 event triggers
      → 执行 callback
        → behavior callback → IM._execute_actions(inst, behavior.actions)
            → action: runScript → sandbox 执行
            → action: triggerEvent → bus.publish
            → action: transition → IM._transition_state(inst, transition)
                → 改变 inst.state["current"]
                → ValueChangedTrigger.handle_value_change("state.current", ...)
                  → 匹配 valueChanged triggers (如 stateEnter)
                    → 执行 callback ...

property 变更 (variables/attributes/derivedProperties)
  → TriggerRegistry.notify_value_change(...)
    → ValueChangedTrigger / ConditionTrigger（duck typing 分发）
      → 匹配 triggers → 执行 callback ...

timer 到期
  → TimerTrigger (内部 TimerScheduler)
    → 匹配 delay/interval/cron triggers
      → 执行 callback ...
```

### Trigger 接口（可扩展）

每种 trigger 类型独立实现。`TriggerRegistry` 持有注册表，在发生注册、注销、数据变更等事件时通知对应的 Trigger 实现。Trigger 实现只负责评估逻辑和回调执行，不管理注册表。

```python
class Trigger(ABC):
    @property
    @abstractmethod
    def trigger_types(self) -> set[str]:
        """返回本 trigger 支持的类型，如 {"event"}、{"delay", "interval", "cron"}"""

    def on_registered(self, entry: TriggerEntry) -> None:
        """TriggerRegistry 完成注册后通知。实现可在此建立内部索引（如 ConditionIndex）。"""
        pass

    def on_unregistered(self, entry: TriggerEntry) -> None:
        """TriggerRegistry 完成注销后通知。实现可在此清理内部索引。"""
        pass

    def on_instance_removed(self, instance) -> None:
        """某个实例被销毁。实现清理与该实例相关的内部状态（如定时器、索引）。"""
        pass

```

**内置 Trigger：**

| Trigger | 支持类型 | 职责 |
|---|---|---|
| `EventTrigger` | `event` | 订阅 EventBus，事件匹配时通过 reg.callback 回调 |
| `ValueChangedTrigger` | `valueChanged` | property 值变更时匹配并回调 |
| `ConditionTrigger` | `condition` | 依赖变更时评估条件表达式，满足窗口条件则回调 |
| `TimerTrigger` | `delay`, `interval`, `cron` | 管理定时器调度，到期时回调 |

### TriggerRegistry（协调层）

```python
class TriggerRegistry:
    def __init__(self):
        self._triggers: dict[str, Trigger] = {}          # type -> trigger 实现
        self._registrations: dict[str, TriggerEntry] = {}   # trigger_id -> entry

    def add_trigger(self, trigger: Trigger) -> None:
        for t in trigger.trigger_types:
            self._triggers[t] = trigger

    def register(self, instance, trigger_cfg, callback, tag) -> str:
        trigger_impl = self._triggers.get(trigger_cfg["type"])
        if trigger_impl is None:
            raise ValueError(f"Unknown trigger type: {trigger_cfg['type']}")
        reg = TriggerEntry(instance, trigger_cfg, callback, tag)
        self._registrations[reg.id] = reg
        trigger_impl.on_registered(reg)
        return reg.id

    def unregister(self, trigger_id: str) -> None:
        reg = self._registrations.pop(trigger_id, None)
        if reg:
            trigger_impl = self._triggers.get(reg.trigger["type"])
            if trigger_impl:
                trigger_impl.on_unregistered(reg)

    def unregister_instance(self, instance) -> None:
        for reg in list(self._registrations.values()):
            if reg.instance is instance:
                self.unregister(reg.id)
        for trigger_impl in self._triggers.values():
            trigger_impl.on_instance_removed(instance)

    # 数据变更入口 —— 只通知关心 value 变更的 trigger 实现（duck typing）
    def notify_value_change(self, instance, field_path, old_val, new_val):
        for trigger_impl in self._triggers.values():
            if hasattr(trigger_impl, "handle_value_change"):
                trigger_impl.handle_value_change(instance, field_path, old_val, new_val)
```

### 级联触发问题（待后续解决）

**问题场景：**
```
event "beat" 到来
  → onBeat behavior: this.variables.count += 1
    → count 变化
      → valueChanged trigger "onCountChanged": alertCount += 1
        → alertCount 变化
          → valueChanged trigger "onAlertCountChanged": ...
            → 无限循环？
```

当 event 触发 behavior actions，actions 修改了 property，导致 valueChanged / condition triggers 被触发，这些 triggers 的 callbacks 又修改了 property，形成级联。本次设计保留此问题描述，解决方案在后续迭代中实现。

### Condition 精确评估机制

**自动解析依赖：**

注册时从 `condition: "this.variables.temperature >= this.attributes.threshold"` 中提取 `watch: ["variables.temperature", "attributes.threshold"]`。

**只检查 property 依赖：** condition 的 watch 只检查 `state`、`variables`、`attributes`、`derivedProperties` 这四类 property 的依赖，其他配置节（如 `metadata`、`links` 等）一概不检查。

**解析方法：**
```python
PROPERTY_SECTIONS = {"state", "variables", "attributes", "derivedProperties"}

def _extract_condition_deps(condition_expr: str) -> list[str]:
    """从条件表达式中提取 this.xxx.yyy 路径，只保留 property 类的依赖。"""
    import re
    matches = re.findall(
        r'this\.([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)',
        condition_expr
    )
    # 只保留 state/variables/attributes/derivedProperties 开头的路径
    return list(set(
        m for m in matches
        if m.split(".")[0] in PROPERTY_SECTIONS
    ))
```

**依赖索引：**
```python
class ConditionIndex:
    def __init__(self):
        self._by_field: dict[str, list[TriggerEntry]] = defaultdict(list)

    def register(self, entry):
        for field in entry.watch:
            self._by_field[field].append(entry)

    def get_affected(self, changed_fields: set[str]) -> list[TriggerEntry]:
        """返回依赖任一变更字段的 condition trigger。"""
        affected = set()
        for field in changed_fields:
            affected.update(self._by_field.get(field, []))
        return list(affected)
```

### 触发器评估顺序（单轮）

收到 event 时的处理顺序：

1. **匹配 event triggers** → 执行匹配的 behavior actions
2. **actions 执行期间**：脚本直接执行，property 变更即时生效
3. **actions 执行完毕后**：本次事件处理结束

**注：** valueChanged 和 condition triggers 的评估时机（即时评估 vs 批处理）在后续迭代中确定。

### Timer 管理

```python
class TimerScheduler:
    """管理 delay / interval / cron triggers 的定时调度。"""

    def register(self, trigger_reg) -> str
    def unregister(self, timer_id)

    # 内部使用 threading.Timer / sched / croniter
    # delay: 一次性 threading.Timer
    # interval: 周期性 threading.Timer 递归
    # cron: croniter 计算下次触发时间，threading.Timer 单次调度
```

## 关键决策

| 决策 | 选择 | 理由 |
|---|---|---|
| stateEnter 统一 | `valueChanged` trigger | 减少概念数量，统一框架 |
| timer 细分 | `delay` / `interval` / `cron` | 语义清晰，配置直观 |
| condition 评估策略 | 自动解析依赖 + 精确追踪 | 快且减少计算 |
| 级联触发处理 | 待后续解决 | 本次聚焦核心框架 |
| delay 语义 | 纯粹推迟，独立排队 | 简单直接 |
| condition 满足后重复 | `repeat: false`（默认） | 避免 spam，需条件不满足后再满足才能再次触发 |
| transition 位置 | 纯状态图定义，去 trigger | 概念清晰，trigger 统一到 behaviors |
| property 命名 | 全局唯一 | variables/attributes/derivedProperties 不允许重名 |
| condition watch 范围 | 只检查 property | 不检查 metadata/links 等其他配置节 |
| metric 实时数据绑定 | 后续独立设计 | 通过实例 `bindings` 字段配置 |
| 向后兼容 | 不考虑 | 全新项目，设计持续迭代，无需兼容旧格式 |

## 与现有运行时集成

1. `WorldRegistry.load_world` 中创建 `TriggerRegistry()` 并注册所有 trigger：
   ```python
   te = TriggerRegistry()
   te.add_trigger(EventTrigger(event_bus))
   te.add_trigger(ValueChangedTrigger())
   te.add_trigger(ConditionTrigger(sandbox))
   te.add_trigger(TimerTrigger())
   ```
2. `IM._register_instance` 调用 `trigger_evaluator.register_instance(inst)`
   - 遍历 inst.model["behaviors"] 中的每个 behavior
   - 对每个 behavior 的 trigger 调用 `te.register(inst, trigger, callback, tag)`
   - callback 为 `lambda inst, behavior=behavior: IM._execute_actions(inst, behavior.actions)`
3. `IM._on_event` 不再需要：EventTriggerHandler 直接订阅 EventBus
4. 新增 `IM._transition_state(inst, transition_name)` 方法供 behavior action 调用
5. `_DictProxy` 增强：记录变更字段列表，变更时调用 `te.notify_value_change(...)`
6. `TimerScheduler` 作为 `TimerTrigger` 的内部组件，管理 delay/interval/cron
