# 代码审查 - 缺陷与改进清单

> 审查范围：全量源代码（src/ + tests/）
> 审查日期：2026-04-25（调整后再次评审）

---

## P0 - 严重缺陷（影响功能正确性，需立即修复）

### P0.1 EventTrigger.on_unregistered 误删同实例所有 event handler

- **文件**: [src/runtime/triggers/event_trigger.py:37-42](src/runtime/triggers/event_trigger.py#L37-L42)
- **问题**: `bus.unregister(instance_id)` 会全局移除该实例在所有 event_type 上的 handler。如果实例注册了多个 behavior（分别监听不同 event_type），注销其中一个会把该实例**所有** event handler 都删掉。
- **根因**: EventBus.unregister 当前只支持按 instance_id 全局移除，不区分 event_type。
- **修复方向**:
  1. EventBus.unregister 增加可选 `event_type` 参数
  2. EventTrigger.on_unregistered 按 `entry.trigger["name"]` 调用细粒度移除
- **状态**: ✅ 已修复 — EventBus.unregister 已支持 `event_type` 参数，EventTrigger 正确按事件类型移除

---

### P0.2 EventBus.publish 中 handler 异常中断后续分发

- **文件**: [src/runtime/event_bus.py:46-51](src/runtime/event_bus.py#L46-L51)
- **问题**: publish 遍历 handlers 直接调用，无异常隔离。一个 behavior 脚本抛异常会中断事件分发，后续所有实例收不到该事件。
- **影响**: 单个 buggy behavior 可导致整个事件总线瘫痪。
- **修复方向**: 每个 handler 调用包 `try/except`，记录日志但不中断循环。
- **状态**: ✅ 已修复 — publish 中 handler 调用已包 try/except + logger.exception

---

### P0.3 InboxProcessor._distribute 中部分失败导致消息丢失

- **文件**: 原 [src/runtime/inbox_processor.py](src/runtime/inbox_processor.py)
- **问题**: 同一 event_type 被多个 world 订阅时，部分发布成功、部分失败。失败的 world 永远收不到消息。
- **状态**: ✅ 已修复 — 通过 Delivery 模型按 world 追踪投递状态，支持 per-world 独立重试/死信

---

### P0.4 InstanceManager.runScript 错误完全静默

- **文件**: [src/runtime/instance_manager.py:193-195](src/runtime/instance_manager.py#L193-L195)
- **问题**: 所有 sandbox 脚本执行错误被吞掉，无任何日志记录。用户无法知道 behavior 脚本为什么失败、失败在哪一行。
- **当前代码**:
  ```python
  except Exception:
      # Swallow sandbox errors to avoid breaking the event bus
      pass
  ```
- **修复方向**: 添加 `logger.exception(...)` 记录完整异常堆栈，保持不中断事件总线的设计。
- **状态**: ❌ 未修复

---

### P0.5 InstanceManager.create 回滚时残留数据库脏数据

- **文件**: [src/runtime/instance_manager.py:326-332](src/runtime/instance_manager.py#L326-L332)
- **问题**: `_register_instance` 失败回滚时，只从内存 `_instances` pop，但此前已调用 `_save_to_store`（第332行），**数据库中残留了脏数据**。
- **修复方向**: 回滚时额外调用 `self._store.delete_instance()` 清理已写入的数据。
- **状态**: ❌ 未修复

---

### P0.6 WorkerManager.unload_world 异常路径导致 world_lock 永久泄露

- **文件**:
  - [src/worker/manager.py:135-148](src/worker/manager.py#L135-L148)
  - [src/runtime/world_registry.py:176-193](src/runtime/world_registry.py#L176-L193)
- **问题**: 正常路径不会双重释放，但异常路径会泄露：
  1. `registry.unload_world()` 中 `state_mgr.shutdown()` 抛异常时，`world_lock.release()` 不会执行
  2. 回到 `WorkerManager.unload_world()` 后，由于 `registry.unload_world()` 已抛异常，也不会执行 fallback 的 `world_lock.release()`
  3. 锁永久泄露，后续任何进程无法加载该 world
- **修复方向**: 统一在 `registry.unload_world()` 中用 try/finally 确保 `world_lock.release()`。
- **状态**: ❌ 未修复（描述已更新，从"双重释放"修正为"异常路径锁泄露"）

---

### P0.7 WorkerManager.handle_command world.start 后 world 生命周期未闭环

- **文件**: [src/worker/manager.py:183-195](src/worker/manager.py#L183-L195)
- **问题**: 动态加载的 world 存在多处生命周期缺失：
  1. **未注册 MessageHub** — 没有调用 `message_hub.register_world()`，外部事件进不来
  2. **未补 bundle["message_hub"]** — 后续 `messageHub.publish` 命令无法找到 hub
  3. **未启动 auto-checkpoint** — 没有调用 `state_mgr.start_async()`，状态不会自动持久化
  4. **未启动 shared scenes** — `run_command.py` 启动时会为每个 world 启动 shared 场景，但 `world.start` 命令没有
- **状态**: ✅ 已修复 — `_bind_world_bundle` + `start_async`

---

### P0.8 MessageHub 生命周期错配 — worker 级单例被 world 级 stop

- **文件**: [src/worker/manager.py](src/worker/manager.py)
- **问题**: MessageHub 是 worker 级单例，但每个 bundle 都持有同一个 hub 引用。当单个 world 被 stop/unload 时，`_graceful_shutdown` 和 `unload_world` 直接调用 `message_hub.stop()`，导致整个 worker 的 channel 被关闭、processor 被取消。
- **状态**: ✅ 已修复 — Worker 级单例，`unregister_world` 管理生命周期，`stop()` 只在 worker 停时调用

---

### P0.9 model_events 空洞 — 外部事件契约完全失效

- **文件**: 原 MessageHub 订阅表相关代码
- **问题**: `bundle` 中没有 `model_events` 字段，`external=True` 永远不会触发。
- **状态**: ✅ 已修复 — 移除 `external=True` 机制，改用显式 `WorldMessageSender`。sandbox 无法发外部事件，安全边界更清晰。

---

### P0.10 路由键缺少 world/tenant 维度 — 多 world 必然串话

- **文件**: 原 inbox/outbox schema
- **问题**: 订阅表和 inbox/outbox 表缺少 `world_id` 列，多 world 场景下消息串话。
- **状态**: ✅ 已修复 — `inbox`/`outbox` 表均有 `world_id` 列，`inbox_deliveries` 按 `target_world_id` 追踪投递状态

---

### P0.11 WorldMessageIngress 的 asyncio.to_thread 可能导致线程池耗尽

- **文件**: [src/runtime/messaging/world_ingress.py:12-20](src/runtime/messaging/world_ingress.py#L12-L20)
- **问题**: `await asyncio.to_thread(self._event_bus.publish, ...)` 将整条事件分发链（包括 behavior 脚本执行）放到线程池运行。当外部消息量大且 behavior 脚本复杂时，会耗尽 `ThreadPoolExecutor`（默认 `min(32, cpu+4)`），阻塞后续所有 `to_thread` 调用。
- **根因**: EventBus.publish 会同步调用所有 behavior handler，而 handler 中可能触发 sandbox 执行。把这些全部塞到 to_thread 是一个隐藏的性能炸弹。
- **修复方向**:
  1. 方案 A: `receive()` 改为直接调用 `publish()`，因为 InboxProcessor 已经按 world 做了串行隔离
  2. 方案 B: 如果必须 to_thread（因 EventBus 使用 threading.RLock），使用自定义线程池并限制并发度
- **状态**: ❌ 未修复

---

### P0.12 StateManager.shutdown 未等待 checkpoint task 完成

- **文件**: [src/runtime/state_manager.py:193-198](src/runtime/state_manager.py#L193-L198)
- **问题**: 注释说"Cancel the auto-checkpoint task and wait for it to finish"，但代码 `cancel()` 后直接设 `None`，没有 `await`。正在进行的 checkpoint 可能写了一半被中断，导致数据库处于不一致状态。
- **当前代码**:
  ```python
  self._task.cancel()
  self._task = None
  ```
- **修复方向**: `cancel()` 后 `await self._task`（处理 CancelledError），确保 checkpoint 完成或安全回滚。
- **状态**: ❌ 未修复（原 P1.3 实际未修复，升级至 P0）

---

## P1 - 重要修复（数据一致性和并发安全）

### P1.1 JsonRpcChannel._pending_requests 并发访问无锁保护

- **文件**: [src/worker/channels/jsonrpc_channel.py:152-163](src/runtime/channels/jsonrpc_channel.py#L152-L163)
- **问题**: `_send_and_wait`（写入字典）与 `_handle_response`（读取并 pop）在不同 asyncio task 中并发执行，没有锁保护，存在 race condition。
- **修复方向**: 用 `asyncio.Lock` 保护 `_pending_requests` 的读写。
- **状态**: ❌ 未修复

---

### P1.2 SQLiteStore.replay_after 使用 timestamp 排序导致恢复顺序不确定

- **文件**: [src/runtime/stores/sqlite_store.py:388-417](src/runtime/stores/sqlite_store.py#L388-L417)
- **问题**: `replay_after` 通过 `timestamp > (...)` 过滤事件。同一毫秒内产生的事件，恢复顺序不确定，可能导致状态恢复不一致。
- **修复方向**: 用自增主键 `rowid`（或显式定义的自增列）替代 `timestamp` 做事件排序和过滤。
- **注意**: 需要修改 `event_log` 表结构，注意已有数据库的迁移兼容性。
- **状态**: ❌ 未修复

---

### P1.3 StateManager.shutdown 取消 task 后未等待完成

- **文件**: [src/runtime/state_manager.py:193-198](src/runtime/state_manager.py#L193-L198)
- **问题**: 直接 `cancel()` 并丢弃引用，没有 `await task`。正在进行的 checkpoint 可能写了一半就被中断，导致数据库处于不一致状态。
- **修复方向**: `cancel()` 后 `await self._task`（处理 CancelledError），确保 checkpoint 完成或安全回滚。
- **状态**: 已并入 P0.12

---

### P1.4 SceneManager._reconcile_properties 空实现

- **文件**: [src/runtime/scene_manager.py:40-44](src/runtime/scene_manager.py#L40-L44)
- **问题**: `derivedProperties` 的重计算逻辑完全缺失，所有依赖它的 snapshot 和 audit 都不准确。
- **当前代码**:
  ```python
  def _reconcile_properties(self, instances: list):
      # TODO: recompute derivedProperties based on current variables/attributes
      for inst in instances:
          inst._update_snapshot()
  ```
- **修复方向**: 遍历 `inst.model.derivedProperties`，用 sandbox 计算表达式，结果写入对应的 section。需先确认表达式语法规范。
- **状态**: ❌ 未修复

---

### P1.5 SceneManager.start 中 shared 场景缺少 metric backfill

- **文件**: [src/runtime/scene_manager.py:102-117](src/runtime/scene_manager.py#L102-L117)
- **问题**: 只有 `mode == "isolated"` 的场景会做 metric backfill，shared 场景跳过了这一步，导致 shared 场景中的实例 metric 变量值不正确。
- **修复方向**: shared 模式也调用 `_backfill_metrics`（注意只 backfill references 中的实例）。
- **状态**: ❌ 未修复

---

### P1.6 EventBus._scope_matches 不支持通配符/层级匹配

- **文件**: [src/runtime/event_bus.py:68-71](src/runtime/event_bus.py#L68-L71)
- **问题**: 当前只支持精确匹配 `msg_scope == inst_scope` 或 `"world"` 广播。不支持 `scene:*` 广播等高级路由场景。
- **修复方向**: 扩展 `_scope_matches` 支持模式匹配（如 `scene:*` 匹配所有 scene 作用域）。
- **状态**: ❌ 未修复

---

### P1.7 external=True 语义二义性 — 抽象泄漏

- **文件**: 原 MessageHub 订阅表代码
- **问题**: `external=True` 同时承担 inbound 和 outbound 两个语义。
- **状态**: ✅ 已修复 — 通过显式 `WorldMessageSender` 替代，不再使用 `external` 标记

---

### P1.8 MessageHub 线程/asyncio 边界无并发保护

- **文件**: [src/runtime/messaging/hub.py](src/runtime/messaging/hub.py)
- **问题**: `_receivers` 等共享状态无锁保护。
- **状态**: ✅ 已修复 — `threading.RLock` 保护 `_receivers`

---

### P1.9 inbox_reconcile_statuses 每次全表扫描

- **文件**: [src/runtime/messaging/sqlite_store.py:274-299](src/runtime/messaging/sqlite_store.py#L274-L299)
- **问题**: `SELECT DISTINCT message_id FROM inbox_deliveries` 是每次 `run_once()` 末尾执行的全表扫描，对每个 message_id 还要再查一次状态。消息量大时性能极差，拖慢整个 InboxProcessor。
- **修复方向**:
  1. 在 inbox_deliveries 上增加一个触发器或计数器列
  2. 或者只在 delivery 状态变化时（delivered/dead）增量更新 inbox 状态
  3. 或者给 inbox 表增加 `pending_delivery_count` / `dead_delivery_count` 列，由数据库触发器维护
- **状态**: ❌ 未修复

---

### P1.10 OutboxProcessor error_count read-modify-write 非原子

- **文件**: [src/runtime/messaging/outbox_processor.py:56](src/runtime/messaging/outbox_processor.py#L56)
- **问题**: 先 `outbox_get_error_count` 读，再 `outbox_mark_retry` 写，非原子。虽然单 processor 不会并发，但设计上有缺陷，未来如果有多个 outbox processor（如分片场景）会出问题。
- **修复方向**: 改为数据库级原子 `UPDATE outbox SET error_count = error_count + 1`。
- **状态**: ❌ 未修复

---

### P1.11 InboxProcessor retry 无指数退避

- **文件**: [src/runtime/messaging/inbox_processor.py:141-143](src/runtime/messaging/inbox_processor.py#L141-L143)
- **问题**: 固定 `retry_delay` 秒（默认 1s），失败消息会持续高频重试，对故障 world 造成压力，可能导致级联故障。
- **修复方向**: 改为 `delay * 2^error_count` capped at max_delay（如 1s → 2s → 4s → ... → 300s）。
- **状态**: ❌ 未修复

---

## P2 - 完善项（健壮性、监控、缺失功能）

### P2.1 OutboxProcessor 对 PERMANENT 失败无死信机制

- **文件**: [src/runtime/messaging/outbox_processor.py:73-78](src/runtime/messaging/outbox_processor.py#L73-L78)
- **问题**: 消息达到永久失败后只标记 `dead`，没有死信队列（DLQ）或通知机制。消息无声消失，运营无法感知。
- **修复方向**: 增加死信表 `dead_letter`，或 PERMANENT 时触发告警事件/回调。
- **状态**: ❌ 未修复

---

### P2.2 Supervisor 启动 worker 后无进程监控

- **文件**: [src/supervisor/server.py:66](src/supervisor/server.py#L66)
- **问题**: `subprocess.Popen(cmd)` 后直接返回，不检查进程是否成功启动、不跟踪 PID、不处理启动失败。worker 崩溃后 Supervisor 无法感知。
- **修复方向**: 获取 PID，定期 `poll()` 检查进程存活；崩溃时清理注册状态，可选自动重启。
- **状态**: ❌ 未修复

---

### P2.3 Supervisor._handle_start 存在竞态条件

- **文件**: [src/supervisor/server.py:54-67](src/supervisor/server.py#L54-L67)
- **问题**: 检查 `get_worker_by_world` 和 `subprocess.Popen` 之间没有原子性保护，并发请求可能 spawn 多个 worker 进程处理同一个 world。
- **修复方向**: 用 `asyncio.Lock` 包裹"查重 + spawn"两段逻辑。
- **状态**: ❌ 未修复

---

### P2.4 TimerTrigger cron 支持未实现

- **文件**: [src/runtime/triggers/timer_trigger.py:101-103](src/runtime/triggers/timer_trigger.py#L101-L103)
- **问题**: cron 触发器留空，仅有一个 `pass`。
- **修复方向**: 引入 `croniter` 库，解析 cron 表达式，用 `TimerScheduler` 的 sleep 机制触发。需更新 `pyproject.toml` 依赖。
- **状态**: ❌ 未修复

---

### P2.5 world.reload 命令未实现

- **文件**: [src/worker/manager.py:197-200](src/worker/manager.py#L197-L200)
- **问题**: 返回 `"not yet implemented"` 错误。无法热更新 world 配置。
- **修复方向**: 卸载旧 world、重新 `registry.load_world`、恢复 MessageHub 注册、重启 checkpoint。
- **状态**: ❌ 未修复

---

### P2.6 AlarmManager 内存状态与数据库不同步

- **文件**: [src/runtime/alarm_manager.py](src/runtime/alarm_manager.py)
- **问题**: `force_clear` 或通过外部 `store.clear_alarm` 清除时，内存中的 `_states` 未同步清理。重启后状态可能不一致。
- **修复方向**: `force_clear` 或收到清除事件时同步从 `_states` 删除对应 key。
- **状态**: ❌ 未修复

---

### P2.7 缺少 Supervisor 健康检查/就绪检查端点

- **文件**: [src/supervisor/server.py](src/supervisor/server.py)
- **问题**: 没有 `/health` 或 `/ready` 端点，无法做负载均衡或 Kubernetes 探针。
- **修复方向**: 添加 `/health` 和 `/ready` HTTP 端点。
- **状态**: ❌ 未修复

---

### P2.8 run_command.py ws_port 参数（Worker WebSocket 服务端）未实现

- **文件**: [src/worker/cli/run_command.py:87-89](src/worker/cli/run_command.py#L87-L89)
- **问题**: `ws_port` 参数留空，TODO 注释说明"Worker-level WebSocket server for direct client connections"。
- **修复方向**: 实现基于 websockets 的本地 JSON-RPC 服务端，复用 `_register_worker_handlers`。
- **状态**: ❌ 未修复

---

### P2.9 INSERT OR IGNORE 静默 dedup

- **文件**:
  - [src/runtime/messaging/sqlite_store.py:99](src/runtime/messaging/sqlite_store.py#L99)
  - [src/runtime/messaging/sqlite_store.py:306](src/runtime/messaging/sqlite_store.py#L306)
- **问题**: `inbox_append` / `outbox_append` 使用 `INSERT OR IGNORE`，当 message_id 冲突时消息被静默丢弃，没有任何反馈。外部系统重发消息时无法知道是否已被消费。
- **修复方向**:
  1. 方案 A: 改为 `INSERT OR REPLACE`（更新 payload）
  2. 方案 B: 改为普通 `INSERT` 并捕获 `sqlite3.IntegrityError`，返回明确的 ack/reject
  3. 方案 C: 入库后返回 `is_duplicate` 标志，由调用方决定是否忽略
- **状态**: ❌ 未修复

---

## 架构设计偏离与建议

### 设计 spec 与当前实现的偏离

| Spec 设计 | 当前实现 | 评价 |
|---|---|---|
| inbox/outbox 无 `world_id` | 有 `world_id` | **优于 spec**，解决了 P0.10 多 world 串话 |
| 订阅表 `event_type→{world_id}` 路由 | 直接按 `envelope.world_id` 路由 | **简化但功能降级**。外部系统必须显式指定目标 world（或 `*` 广播），无法表达"谁订阅了谁接收" |
| `pre_publish_hook` 自动写 outbox | 完全移除，只有显式 `WorldMessageSender` | **安全性提升，但功能缺失**。behavior 脚本目前无法访问 `WorldMessageSender`，内部 event 没有任何机制自动外发 |
| 内存订阅表维护 | 不存在 | 外部消息路由完全依赖消息自带的 `world_id` |

### 建议的架构改进

1. **将 `WorldMessageSender` 注入 sandbox context**：当前 behavior 脚本通过 `dispatch()` 只能发内部 event，无法发外部 message。如果产品需要"behavior 触发外部通知"，需要把 sender 以某种名称（如 `send_message` 或 `hub`）注入 sandbox。

2. **InboxProcessor 的 world_id == "*" 广播语义改进**：当前 expand 时 snapshot world 列表。如果 world 在 expand 后注册，它收不到消息；如果 expand 后 unregister，它的 delivery 会进 retry/dead。建议增加机制：pending delivery 发现 receiver 为 None 时不立刻 retry，而是延迟检查。

3. **MessageHub 的 `is_ready()` 语义**：当 `channel=None` 时返回 `True`。这在测试中可以工作，但生产环境中如果 channel 初始化失败（如 Supervisor 不可达），`is_ready()` 应该反映这个状态。

---

## 附录：修复优先级建议

### 第一批（P0，可一次完成）
1. P0.4 — runScript 错误日志
2. P0.5 — create 回滚脏数据
3. P0.6 — 异常路径锁泄露（registry.unload_world try/finally）
4. P0.11 — WorldMessageIngress to_thread 线程池耗尽
5. P0.12 — StateManager.shutdown 等待 task

### 第二批（P1）
6. P1.1 — JsonRpcChannel 并发锁
7. P1.2 — replay_after 确定性排序
8. P1.4 — derivedProperties 实现（需先对齐规范）
9. P1.5 — shared 场景 metric backfill
10. P1.9 — inbox_reconcile_statuses 全表扫描优化
11. P1.10 — Outbox error_count 原子更新
12. P1.11 — 指数退避

### 第三批（P2）
13. P2.1 — 死信队列/通知
14. P2.2 + P2.3 — Worker 进程监控 + 启动竞态
15. P2.4 — cron 支持
16. P2.5 — world.reload
17. P2.6 — AlarmManager 状态同步
18. P2.7 — 健康检查端点
19. P2.8 — Worker WebSocket 服务端
20. P2.9 — INSERT OR IGNORE 去静默化
