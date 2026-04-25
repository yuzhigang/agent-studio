# cron Trigger 实现设计

## 背景

`TimerTrigger` 当前已支持 `delay` 和 `interval` 两种时间触发器，`cron` 分支留空待实现。本设计补充 `cron` 触发器的完整实现，使其与现有 `TimerTrigger` / `TimerScheduler` 两层架构对齐。

## 目标

- 实现基于 cron 表达式的定时触发。
- 支持 `count` 限制（触发指定次数后自动停止）。
- 复用现有的 `TimerScheduler` 调度层，保持 `TimerTrigger` 只负责 entry-to-timer 映射。
- 基于本地系统时间（datetime.now）。

## 架构

在现有两层架构基础上扩展：

- **`TimerScheduler`**：新增 `schedule_cron(cron_expr, callback, count=-1) -> str` 方法。内部使用 `croniter` 计算下次触发时间，启动一个 asyncio task 做等待-触发-重调度循环。cancel/cancel_all 机制与现有 timer 统一。
- **`TimerTrigger`**：`on_registered` 的 `cron` 分支调用 `schedule_cron`，维护相同的 `entry.id -> timer_id` 和 `timer_id -> {entry, instance}` 映射。`on_unregistered`/`on_instance_removed` 无需改动。
- **依赖**：`pyproject.toml` 添加 `croniter`（标准 5 字段 cron 解析库，设计文档原已提及）。

## 调度循环

`schedule_cron` 启动一个 asyncio task，循环如下：

1. 用 `croniter(cron_expr, base_time=datetime.now())` 初始化。
2. 计算 `next_time = croniter.get_next(datetime)`。
3. `await asyncio.sleep((next_time - now).total_seconds())`。
4. 检查 timer_id 是否仍在 `_tasks` 中（可能已被 cancel），不在则退出循环。
5. 执行 `callback()`。异常吞掉（与 delay/interval 一致）。
6. 如果配置了 `count > 0`，递增计数器；达到则 cancel 自己并退出。
7. 跳回步骤 2 计算下一次。

### 边界情况

- **错过触发窗口**：如果 sleep 醒来时已经错过了 `next_time`（例如系统休眠后唤醒），下一次计算仍然基于当前时间 `datetime.now()`，croniter 会自动跳到下一个合法时间点。不会补偿性批量触发。
- **极短间隔**：如果 cron 表达式解析出的间隔极短（如 `* * * * *`），行为与 `interval=60s` 类似，靠 asyncio.sleep 自然排队。
- **unregister 时的竞态**：cancel 只在 sleep 之间有效。如果 callback 正在执行时被 cancel，该次 callback 仍会执行完；这是 asyncio task cancel 的标准行为，与 delay/interval 一致。

## 配置与 API

```yaml
# schedules.yaml 中的用法（已存在）
checkTemperature:
  name: checkTemperature
  cron: '*/5 * * * *'
  actions: [...]
```

TriggerEntry 的 trigger dict 示例：

```python
{"type": "cron", "name": "checkTemperature", "cron": "*/5 * * * *", "count": 5}
```

- `cron`: 必填，标准 5 字段表达式。
- `count`: 可选，默认 -1（无限循环）。
- `name`: 用于日志/调试标识。

## 错误处理

- **无效 cron 表达式**：`croniter` 在构造时会抛出 `ValueError`/`KeyError`。在 `TimerTrigger.on_registered` 中捕获并转化为 `ValueError(f"Invalid cron expression: {cron_expr}")`，让调用方（`TriggerRegistry` 或加载流程）决定如何处理。
- **callback 异常**：`schedule_cron` 的 runner 中吞掉 callback 异常（`except Exception: pass`），与 delay/interval 行为一致。
- **cancel 竞态**：`timer_id` 从 `_tasks` 移除后再检查存在性，避免 double cancel。

## 测试覆盖

在 `tests/runtime/test_timer_trigger.py` 中新增：

- `test_cron_trigger_fires_at_next_tick`：使用 `*/1 * * * *` 配合 `0.5s` sleep，验证 callback 在期望时间点触发。
- `test_cron_trigger_with_count_stops_after_n`：配置 `count=2`，验证只触发 2 次后自动停止。
- `test_cron_trigger_unregistered_cancels`：注册后 unregister，验证不会触发。
- `test_cron_trigger_instance_removed_cancels`：注册后 remove instance，验证不会触发。
- `test_cron_invalid_expression_raises`：传入 `"not-a-cron"`，验证 `ValueError`。

测试策略：由于真实 cron 需要等待分钟级，测试中使用较短的 cron 表达式（如 `*/1 * * * *`）配合 `0.5s` sleep。更可靠的方式是在测试中 patch `datetime.now` 或直接 patch `croniter.get_next` 返回固定时间序列，使测试确定且快速。
