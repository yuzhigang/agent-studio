# Scene Lifecycle Design

## Status

Confirmed for implementation on 2026-06-04.

## Context

The current runtime uses `SceneManager._scenes` as the in-memory collection of
running scenes. However, `SceneManager.stop()` also deletes the persisted scene
definition. This makes stop behave as permanent removal and prevents a stopped
scene from restarting with its original mode, references, and local instance
configuration.

Scene definitions may originate from either:

- `worlds/<world_id>/scenes/**/*.yaml`
- runtime creation persisted only in SQLite

World loading imports YAML scene definitions into SQLite. Therefore, removing
only the SQLite definition is not permanent for YAML-declared scenes because
the YAML definition will be imported again on the next world load.

This phase separates scene runtime lifecycle from scene definition lifecycle.

## Goals

1. Make `stop` affect running scene instances without deleting the definition.
2. Preserve world-scope instances referenced by shared scenes.
3. Stop every scene-scope instance owned by an isolated scene.
4. Stop scene-local instances owned by a shared scene.
5. Allow stopped scenes to restart from their persisted definition.
6. Add `remove` for permanent definition deletion from SQLite and YAML.
7. Expose stopped and running definitions through scene listing.

## Non-Goals

- Changing how scene reference auto-pull works.
- Changing copy-on-write behavior inside isolated scenes.
- Introducing a third in-memory scene-definition registry.
- Implementing transactional coordination across SQLite and the filesystem.
- Changing world-scope instance lifecycle.
- Adding scene creation or update APIs.

## State Model

Scene runtime state and scene definition state are separate:

- `SceneManager._scenes` contains only running scenes.
- SQLite contains all known scene definitions, both running and stopped.
- YAML contains source-controlled definitions when the scene was declared by a
  file.

A scene is:

- `running` when its `(world_id, scene_id)` key exists in `_scenes`.
- `stopped` when its definition exists in SQLite but its key does not exist in
  `_scenes`.
- `absent` when no running scene, SQLite definition, or matching YAML
  declaration exists.

SQLite is the runtime definition source used by `start` and scene listing.
YAML remains the durable declaration source imported during world loading.

## Stop Semantics

`SceneManager.stop(world_id, scene_id)` only stops a running scene.

For every mode:

1. Resolve the scene from `_scenes`.
2. Remove all instances whose scope is exactly `scene:<scene_id>`.
3. Remove the scene from `_scenes`.
4. Keep the SQLite definition.
5. Keep any YAML definition.

This single scope-based cleanup produces the required ownership behavior:

- Shared scene references are world-scope instances and remain running.
- Shared scene local instances use `scene:<scene_id>` and are stopped.
- Isolated reference copies use `scene:<scene_id>` and are stopped.
- Isolated local instances use `scene:<scene_id>` and are stopped.

Stopping an absent or already stopped scene returns `False`. It does not delete
its definition.

The scene remains in `_scenes` until all scene-scope instances have been
successfully removed. If instance cleanup raises, stop propagates the error and
does not report the scene as stopped.

## Start Semantics

`SceneManager.start()` remains the low-level operation that starts a scene from
explicit mode, references, and local instance configuration.

The worker `scene.start` command becomes definition-driven:

1. Return `already_running` when the scene exists in `_scenes`.
2. Load the definition from SQLite.
3. Return `scene_not_found` when no definition exists.
4. Call `SceneManager.start()` with the persisted mode, references, and local
   instance configuration.

Starting a stopped scene therefore recreates its isolated copies or local
instances using the original persisted definition.

`SceneManager.start()` continues to persist the definition after successful
startup. Existing world startup behavior that automatically starts shared
scene definitions remains unchanged.

## Definition Integrity

`SceneManager.start()` currently replaces `scene["local_instances"]` with a map
from local ID to runtime instance ID before persisting. That representation
cannot recreate local instances because it loses each local instance's model
and variable configuration.

This phase changes the running scene record and persisted definition to retain
the complete local instance specification:

```python
{
    "local-id": {
        "modelName": "model-id",
        "agentNamespace": "optional.namespace",
        "variables": {},
    }
}
```

Runtime instances remain discoverable through their `scene:<scene_id>` scope;
the definition does not store runtime object IDs.

Existing persisted definitions that contain the legacy local-ID-to-runtime-ID
map cannot be restarted because they lack `modelName`. Starting such a scene
fails with a clear invalid-definition error instead of inventing a model.

## Remove Semantics

`SceneManager.remove(world_id, scene_id, scenes_dir)` permanently deletes a
scene definition.

### Preflight

Before changing runtime or persisted state:

1. Determine whether a running scene or SQLite definition exists.
2. Recursively scan `scenes_dir` for `*.yaml`.
3. Parse each YAML file and collect files whose top-level `scene_id` exactly
   matches the requested scene ID.
4. If more than one YAML file matches, raise an ambiguity error and make no
   changes.
5. If no running scene, SQLite definition, or YAML match exists, return
   `False`.

Malformed or unreadable YAML encountered during the scan raises an error. The
operation does not assume that such a file is unrelated because its scene ID
cannot be verified.

### Execution order

After successful preflight:

1. If the scene is running, call `stop()`.
2. If a unique YAML declaration exists, delete that file.
3. Delete the SQLite definition.
4. Return `True`.

Filesystem and SQLite deletion cannot form one atomic transaction with the
current store API. YAML is deleted before SQLite because a remaining YAML file
would recreate the SQLite definition on restart. If SQLite deletion fails
after YAML deletion, `remove` raises the store error; the YAML deletion remains
effective and the stale SQLite row can be removed by retrying `remove`.

If YAML deletion fails, SQLite remains unchanged and `remove` raises the
filesystem error.

Runtime-only scenes have no YAML match and delete only the SQLite definition.

## API Changes

### Worker JSON-RPC

Add:

- `scene.remove`

The command requires `world_id` and `scene_id`, calls
`SceneManager.remove()`, and returns:

```json
{"status": "removed"}
```

When no definition exists, it raises the existing scene-not-found JSON-RPC
error code `-32002`.

The command derives `scenes_dir` from the loaded SQLite store's world directory
and passes it to `SceneManager.remove()`. This keeps scene YAML discovery tied
to the loaded world without adding a new world-bundle contract in this phase.

`scene.start` loads the SQLite definition and no longer defaults to isolated
mode.

### Supervisor REST

Add:

- `DELETE /api/worlds/{world_id}/scenes/{scene_id}`

The handler proxies `scene.remove`. A missing scene returns the same
scene-not-found HTTP mapping used by stop.

### Scene listing

`world.scenes.list` lists SQLite definitions rather than only `_scenes`.
Each item contains:

- `scene_id`
- `mode`
- `status`: `running` or `stopped`
- `instance_count`: count of current `scene:<scene_id>` instances

This keeps shared world-scope references out of `instance_count`, consistent
with the existing API.

## World Shutdown

World graceful shutdown continues to operate only on scenes returned by
`SceneManager.list_by_world()`, which are running scenes.

- Stopping shared scenes removes only their scene-local instances.
- Stopping isolated scenes removes every scene-scope instance.
- Persisted definitions survive world shutdown.
- The existing force-stop check still applies only to running isolated scenes.

## Error Handling

- Stop of an absent or already stopped scene returns `False`.
- Start of a missing definition returns scene-not-found.
- Start of a malformed legacy local-instance definition raises an
  invalid-definition error.
- Remove of an absent scene returns `False`.
- Remove with duplicate YAML declarations raises an ambiguity error before
  stopping or deleting anything.
- Remove propagates YAML parsing, filesystem deletion, and SQLite deletion
  errors.

## Implementation Boundaries

Expected production files:

- `src/runtime/scene_manager.py`
- `src/worker/commands/scene.py`
- `src/worker/commands/__init__.py`
- `src/supervisor/handlers/scenes.py`
- `src/supervisor/handlers/__init__.py`
- `src/supervisor/server.py`

Expected focused test files:

- `tests/runtime/test_scene_manager.py`
- `tests/runtime/test_world_instance_scene_integration.py`
- `tests/runtime/test_world_registry.py`
- `tests/worker/test_commands.py`
- supervisor handler or server routing tests

Changes outside these boundaries require a direct dependency on an acceptance
criterion below.

## Acceptance Criteria

1. Stopping a shared scene preserves all referenced world-scope instances.
2. Stopping a shared scene removes every scene-local instance.
3. Stopping an isolated scene removes every instance in its scene scope.
4. Stop removes the scene from the running set but preserves SQLite and YAML
   definitions.
5. A stopped scene restarts with its original mode, references, and complete
   local instance specifications.
6. Starting a missing scene returns scene-not-found rather than creating an
   isolated scene.
7. Scene listing includes stopped definitions and reports accurate status and
   scene-scope instance counts.
8. Removing a running scene stops it before deleting its definition.
9. Removing a YAML-declared scene deletes both the unique matching YAML file
   and SQLite definition, so world reload does not recreate it.
10. Removing a runtime-only scene deletes its SQLite definition.
11. Duplicate or unreadable YAML declarations cause remove to fail before
    runtime or persisted state is changed.
12. Existing focused scene, world shutdown, worker command, and supervisor API
    tests continue to pass except for independently documented pre-existing
    failures outside this phase.
