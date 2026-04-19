# Alarm Persistence Design

## Overview

将告警实例（AlarmState）持久化到 `runtime.db`，支持告警历史审计、时间范围查询和手动清除。

## Goals

1. 每条告警生命周期（触发→清除）对应一条持久化记录，重复触发合并到同一条记录。
2. `alarmTriggered`/`alarmCleared` 事件触发时同步持久化。
3. 支持按时间范围、状态、实例过滤查询告警。
4. 支持用户手动清除活跃告警（`force_clear`）。

## Non-Goals

1. 实例删除时不级联删除告警历史（标记为 TODO，后续设计清理策略）。
2. 不实现告警通知路由（邮件/短信/Webhook），仅持久化告警本身。

---

## Database Schema

新增 `alarms` 表到每个 world 的 `runtime.db`：

```sql
CREATE TABLE IF NOT EXISTS alarms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    world_id TEXT NOT NULL,
    instance_id TEXT NOT NULL,
    alarm_id TEXT NOT NULL,
    category TEXT,
    severity TEXT,
    level INTEGER,
    state TEXT NOT NULL,
    trigger_count INTEGER DEFAULT 0,
    trigger_message TEXT,
    clear_message TEXT,
    triggered_at TEXT,
    cleared_at TEXT,
    payload TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE (world_id, instance_id, alarm_id)
);

CREATE INDEX IF NOT EXISTS idx_alarms_triggered_at
    ON alarms (world_id, triggered_at);

CREATE INDEX IF NOT EXISTS idx_alarms_state
    ON alarms (world_id, state);
```

### Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `id` | INTEGER PK | 自增主键 |
| `world_id` | TEXT | 所属 world |
| `instance_id` | TEXT | 触发告警的实例 ID |
| `alarm_id` | TEXT | 告警配置中的 key（如 `overheat.warning`） |
| `category` | TEXT | 告警分类 |
| `severity` | TEXT | `critical` / `warning` / `info` |
| `level` | INTEGER | 数值级别 |
| `state` | TEXT | `active` / `inactive` |
| `trigger_count` | INTEGER | 当前生命周期内总触发次数（含首次） |
| `trigger_message` | TEXT | `triggerMessage` 模板渲染后的文本 |
| `clear_message` | TEXT | `clearMessage` 模板渲染后的文本 |
| `triggered_at` | TEXT ISO | 首次触发时间 |
| `cleared_at` | TEXT ISO | 清除时间（未清除为 NULL） |
| `payload` | TEXT JSON | `triggerMessage` 中用到的变量快照 |
| `updated_at` | TEXT ISO | 最后更新时间 |

---

## Persistence Lifecycle

```
        ┌─────────────────────────────────────────────┐
        │                                             │
        ▼                                             │
   ┌─────────┐  trigger fires     ┌────────┐         │
   │inactive │ ──────────────────▶│ active │─────────┘
   └─────────┘   UPSERT record    └────────┘  UPDATE
                                       │      trigger_count++
                                       │ clear fires
                                       ▼
                                 ┌──────────┐
                                 │ inactive │
                                 └──────────┘
                                   UPDATE record
                                   state='inactive'
```

### Persistence Triggers

| 场景 | 动作 | SQL |
|------|------|-----|
| 首次触发（`inactive → active`） | UPSERT | `INSERT ... ON CONFLICT(world_id, instance_id, alarm_id) DO UPDATE SET state='active', triggered_at=..., trigger_count=1, cleared_at=NULL, ...` |
| 重复触发（`active → active`，静默过期） | UPDATE | `UPDATE ... SET trigger_count = trigger_count + 1, updated_at = ...` |
| 自动清除（clear trigger 触发） | UPDATE | `UPDATE ... SET state='inactive', cleared_at = ..., updated_at = ...` |
| 手动清除（`force_clear`） | UPDATE + notify | 同自动清除，额外发布 `alarmCleared` 事件 |

### Payload 内容

`payload` 是触发时刻 `triggerMessage` 中用到的变量快照。提取方式：

1. 解析 `triggerMessage` 中的 `{var}` 占位符
2. 从 `instance.variables` → `instance.attributes` → `instance.state` 顺序查找匹配值
3. 将结果编码为 JSON

示例：
```yaml
triggerMessage: "温度 {temperature}℃ 超过阈值 {threshold}℃"
```
提取后 payload：
```json
{"temperature": 95.0, "threshold": 80.0}
```

---

## Store Interface

在 `src/runtime/stores/base.py` 新增：

```python
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
```

---

## AlarmManager Changes

### 新增 `force_clear` 方法

```python
def force_clear(self, instance, alarm_id: str) -> bool:
    """手动清除活跃告警。

    更新内存状态、持久化数据库、发布 alarmCleared 事件。
    如果告警已经是 inactive，返回 False。
    """
    state = self._get_state(instance, alarm_id)
    if state.state != "active":
        return False

    # 获取配置（从 instance.model 读取）
    config = self._get_alarm_config(instance, alarm_id)

    # 更新内存状态
    state.state = "inactive"
    state.cleared_at = self._now()
    state.silence_expires_at = None

    # 发布事件 + 持久化
    self._notify_clear(state, config, instance)
    self._persist_alarm_state(instance, alarm_id, config, is_clear=True)

    return True
```

### 持久化调用时机

在现有 `_on_trigger` 和 `_on_clear` 中增加持久化调用：

```python
def _on_trigger(self, instance, alarm_id: str, config: dict) -> None:
    # ... 现有逻辑 ...
    # 最后一步：持久化
    self._persist_alarm_state(instance, alarm_id, config, is_clear=False)

def _on_clear(self, instance, alarm_id: str, config: dict) -> None:
    # ... 现有逻辑 ...
    # 最后一步：持久化
    self._persist_alarm_state(instance, alarm_id, config, is_clear=True)
```

---

## Why Persist at alarmTriggered/alarmCleared Events

1. **状态变化即持久化**：`_on_trigger` 和 `_on_clear` 是告警状态发生变更的唯一入口，在这里写库是最自然、最不会遗漏的。
2. **直接访问 AlarmState**：在回调内部可以直接拿到 `trigger_count`、`triggered_at` 等内存状态，无需从事件 payload 中重建。
3. **与事件发布同步**：持久化和 `event_bus.publish("alarmTriggered"/"alarmCleared")` 在同一事务中，保证内存、事件、数据库三者一致。

---

## Open Questions

| 问题 | 决策 | 备注 |
|------|------|------|
| 实例删除时是否删除告警历史 | **保留，暂不处理** | 已记录到 `todo.md`，后续设计批量清理策略 |
| `payload` 粒度 | **triggerMessage 用到的变量** | 不存完整快照，避免数据膨胀 |
| `reason` 字段 | **不需要** | `triggerMessage` 渲染后的文本已足够 |
| 手动清除后 trigger 再次满足 | **重新触发新告警周期** | 正确行为——问题未解决则重新告警 |

---

## Backwards Compatibility

- 新增表在 `SQLiteStore._ensure_schema()` 中通过 `IF NOT EXISTS` 创建，不影响已有 world。
- `AlarmManager` 的 `_store` 参数已可接受 `None`，当 `store` 为 `None` 时跳过持久化（纯内存模式兼容）。
