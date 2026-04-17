# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

- **Run all tests**: `pytest tests/ -v`
- **Run a single test**: `pytest tests/path/test_file.py::test_name -v`
- **Run message-related tests**: `pytest tests/runtime/test_event_bus.py tests/runtime/test_message_hub.py tests/runtime/test_inbox_processor.py tests/runtime/test_outbox_processor.py tests/runtime/stores/test_message_store.py -v`
- **Run a project**: `python -m src.cli.main run --project-dir path/to/project`
- **Run multiple projects inline**: `python -m src.cli.main run-inline --project-dir path/to/proj1 --project-dir path/to/proj2`
- **Start supervisor**: `python -m src.cli.main supervisor --base-dir projects --ws-port 8001 --http-port 8080`

The project uses `pytest` with the `anyio` plugin for async tests. `pyproject.toml` configures `pythonpath = ["."]` and `addopts = "--import-mode=importlib"`. Many async tests use `@pytest.mark.anyio` and rely on the `anyio_backend` fixture in `tests/conftest.py` returning `"asyncio"`.

## High-Level Architecture

### Three-Tier Structure

1. **CLI** (`src/cli/main.py`): Entry point dispatching to worker or supervisor commands.
2. **Worker** (`src/worker/`): Runs one or more projects. Communicates with external systems via `Channel` abstractions (`JsonRpcChannel` over WebSocket, `RabbitMQChannel`).
3. **Supervisor** (`src/supervisor/`): Management plane that tracks active worker runtimes via WebSocket and exposes a gateway for external events.
4. **Runtime** (`src/runtime/`): Core engine: project registry, instance/scene/state managers, event bus, message hub, and SQLite stores.

### Project Bundle Pattern

`ProjectRegistry.load_project(project_id)` returns a **bundle dict** containing all per-project services: `store` (SQLiteStore), `event_bus_registry` (EventBusRegistry), `instance_manager`, `scene_manager`, `state_manager`, `project_yaml`, etc. This bundle is passed around in worker CLI code and JSON-RPC handlers.

### Event Bus and Scoping

`EventBus` (`src/runtime/event_bus.py`) routes events by `event_type` and `scope`. Scope can be `"project"` (delivers to all instances) or `"scene:<scene_id>"` (delivers only to instances registered with that scope). Instances register themselves via `InstanceManager._register_instance` when created or loaded.

### Instance Lifecycle and Behaviors

`InstanceManager` creates `Instance` objects (dataclass in `src/runtime/instance.py`). Each instance is associated with a **model** loaded by `ModelLoader`. Models define **behaviors** (event triggers → actions). Actions are either `runScript` (executed in `SandboxExecutor`) or `triggerEvent` (dispatches another event). The `dispatch` function injected into sandbox context prefers `message_hub.publish` if a hub is attached, otherwise falls back to `event_bus.publish`.

### Scenes: Shared vs Isolated

`SceneManager.start(project_id, scene_id, mode)` supports two modes:
- **shared**: References existing project-scoped instances. No copies are made.
- **isolated**: Creates copy-on-write (deep copy) scene-scoped instances via `InstanceManager.copy_for_scene`. Stopping an isolated scene removes all scene-scoped instances.

Scene start also performs **metric backfill** (from `metric_store`) and **property reconciliation** (`_reconcile_properties`) on the assembled instances.

### State Management: Checkpoint and Restore

`StateManager` runs a background thread that auto-checkpoints every 30 seconds. `checkpoint_project` persists all active/completed instances to `instance_store` and updates `project_state`. `restore_project` loads instances from the store and then **replays events** from `event_log_store` after the last checkpointed `last_event_id`. This is the primary recovery mechanism.

### Storage Separation

- **`runtime.db`** (project-level, via `SQLiteStore`): Holds `projects`, `scenes`, `instances`, `event_log`, `project_state`.
- **`messagebox.db`** (worker-level, via `SQLiteMessageStore`, *under active refactor*): Holds `inbox` and `outbox` for external event buffering. The codebase is transitioning MessageHub from **per-project** to **per-worker** architecture per `docs/superpowers/specs/2026-04-16-message-hub-worker-level-design.md`.

### MessageHub Refactor (In Progress)

The current transition moves MessageHub from being constructed per-project (inside `run_command.py` / `run_inline.py`) to a **worker-level singleton** that:
- Registers multiple projects via `register_project(project_id, event_bus, model_events)`
- Intercepts external events via `EventBus.pre_publish_hook`
- Routes inbound messages via an in-memory subscription table (`event_type -> {project_id, ...}`)
- Uses a single `InboxProcessor` / `OutboxProcessor` and one `Channel` per worker

When modifying MessageHub, InboxProcessor, OutboxProcessor, or worker CLI startup code, ensure alignment with this worker-level design spec.

### Sandbox Security

`SandboxExecutor` (`src/runtime/lib/sandbox.py`) restricts behavior scripts to a whitelist of safe builtins (`SAFE_BUILTINS`) and a set of preloaded modules (`math`, `random`, `json`, `datetime`, etc.). Shared library functions registered in `LibRegistry` are injected into the sandbox as dynamically created modules. Forbidden builtins like `open`, `eval`, `exec`, `__import__` are blocked.

### Channels and SendResult

All channels implement `Channel` (`src/worker/channels/base.py`) with `start(inbound_callback)`, `send(...) -> SendResult`, and `stop()`. `SendResult` has three outcomes: `SUCCESS`, `RETRYABLE` (exponential backoff in OutboxProcessor), and `PERMANENT` (marks message as dead).

## Tool Usage Note

When writing large files with the `Write` tool, break the content into smaller chunks or use `Edit` for incremental updates to avoid failures caused by oversized payloads.
