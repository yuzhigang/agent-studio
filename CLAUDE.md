# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

- **Run all tests**: `pytest tests/ -v`
- **Run a single test**: `pytest tests/path/test_file.py::test_name -v`
- **Run message-related tests**: `pytest tests/runtime/test_event_bus.py tests/runtime/test_message_hub.py tests/runtime/test_inbox_processor.py tests/runtime/test_outbox_processor.py tests/runtime/stores/test_message_store.py -v`
- **Run a world**: `python -m src.cli.main run --world-dir path/to/world`
- **Run multiple worlds inline**: `python -m src.cli.main run-inline --world-dir path/to/proj1 --world-dir path/to/proj2`
- **Start supervisor**: `python -m src.cli.main supervisor --base-dir worlds --ws-port 8001 --http-port 8080`

The world uses `pytest` with the `anyio` plugin for async tests. `pyproject.toml` configures `pythonpath = ["."]` and `addopts = "--import-mode=importlib"`. Many async tests use `@pytest.mark.anyio` and rely on the `anyio_backend` fixture in `tests/conftest.py` returning `"asyncio"`.

## High-Level Architecture

### Three-Tier Structure

1. **CLI** (`src/cli/main.py`): Entry point dispatching to worker or supervisor commands.
2. **Worker** (`src/worker/`): Runs one or more worlds. Communicates with external systems via `Channel` abstractions (`JsonRpcChannel` over WebSocket, `RabbitMQChannel`).
3. **Supervisor** (`src/supervisor/`): Management plane that tracks active worker runtimes via WebSocket and exposes a gateway for external events.
4. **Runtime** (`src/runtime/`): Core engine: world registry, instance/scene/state managers, event bus, message hub, and SQLite stores.

### World Bundle Pattern

`WorldRegistry.load_world(world_id)` returns a **bundle dict** containing all per-world services: `store` (SQLiteStore), `event_bus_registry` (EventBusRegistry), `instance_manager`, `scene_manager`, `state_manager`, `world_yaml`, etc. This bundle is passed around in worker CLI code and JSON-RPC handlers.

### Event Bus and Scoping

`EventBus` (`src/runtime/event_bus.py`) routes events by `event_type` and `scope`. Scope can be `"world"` (delivers to all instances) or `"scene:<scene_id>"` (delivers only to instances registered with that scope). Instances register themselves via `InstanceManager._register_instance` when created or loaded.

### Instance Lifecycle and Behaviors

`InstanceManager` creates `Instance` objects (dataclass in `src/runtime/instance.py`). Each instance is associated with a **model** loaded by `ModelLoader`. Models define **behaviors** (event triggers → actions). Actions are either `runScript` (executed in `SandboxExecutor`) or `triggerEvent` (dispatches another event). The `dispatch` function injected into sandbox context prefers `message_hub.publish` if a hub is attached, otherwise falls back to `event_bus.publish`.

### Scenes: Shared vs Isolated

`SceneManager.start(world_id, scene_id, mode)` supports two modes:
- **shared**: References existing world-scoped instances. No copies are made.
- **isolated**: Creates copy-on-write (deep copy) scene-scoped instances via `InstanceManager.copy_for_scene`. Stopping an isolated scene removes all scene-scoped instances.

Scene start also performs **metric backfill** (from `metric_store`) and **property reconciliation** (`_reconcile_properties`) on the assembled instances.

### State Management: Checkpoint and Restore

`StateManager` runs a background thread that auto-checkpoints every 30 seconds. `checkpoint_world` persists all active/completed instances to `instance_store` and updates `world_state`. `restore_world` loads instances from the store and then **replays events** from `event_log_store` after the last checkpointed `last_event_id`. This is the primary recovery mechanism.

### Storage Separation

- **`runtime.db`** (world-level, via `SQLiteStore`): Holds `worlds`, `scenes`, `instances`, `event_log`, `world_state`.
- **`messagebox.db`** (worker-level, via `SQLiteMessageStore`, *under active refactor*): Holds `inbox` and `outbox` for external event buffering. The codebase is transitioning MessageHub from **per-world** to **per-worker** architecture per `docs/superpowers/specs/2026-04-16-message-hub-worker-level-design.md`.

### MessageHub Refactor (In Progress)

The current transition moves MessageHub from being constructed per-world (inside `run_command.py` / `run_inline.py`) to a **worker-level singleton** that:
- Registers multiple worlds via `register_world(world_id, event_bus, model_events)`
- Intercepts external events via `EventBus.pre_publish_hook`
- Routes inbound messages via an in-memory subscription table (`event_type -> {world_id, ...}`)
- Uses a single `InboxProcessor` / `OutboxProcessor` and one `Channel` per worker

When modifying MessageHub, InboxProcessor, OutboxProcessor, or worker CLI startup code, ensure alignment with this worker-level design spec.

### Sandbox Security

`SandboxExecutor` (`src/runtime/lib/sandbox.py`) restricts behavior scripts to a whitelist of safe builtins (`SAFE_BUILTINS`) and a set of preloaded modules (`math`, `random`, `json`, `datetime`, etc.). Shared library functions registered in `LibRegistry` are injected into the sandbox as dynamically created modules. Forbidden builtins like `open`, `eval`, `exec`, `__import__` are blocked.

### Channels and SendResult

All channels implement `Channel` (`src/worker/channels/base.py`) with `start(inbound_callback)`, `send(...) -> SendResult`, and `stop()`. `SendResult` has three outcomes: `SUCCESS`, `RETRYABLE` (exponential backoff in OutboxProcessor), and `PERMANENT` (marks message as dead).

## Tool Usage Note

When writing large files with the `Write` tool, break the content into smaller chunks or use `Edit` for incremental updates to avoid failures caused by oversized payloads.

## Note
- 不考虑任何关于向后兼容的设计目标和代码逻辑， 因为这是全新的项目，不断在调整设计，没有必要兼容过去的设计。
- 重要的类或文件在文件头给出精要的注释。
- 如果你的内容太长，写入不成功。建议你分为多次写入， 使用edit等工具追加。
- 以无情审问的方式采访我，直到我们达成共识。逐一追究设计树的每个分支，一个一个地解决依赖关系。对每个问题提供你的推荐答案。每次只问一个问题。
- 编码前思考：不要假设。不要隐藏困惑。呈现权衡。
- 简洁优先：用最少的代码解决问题。不要过度推测。
- 精准修改：只碰必须碰的。只清理自己造成的混乱。
- 目标驱动执行：定义成功标准。循环验证直到达成。