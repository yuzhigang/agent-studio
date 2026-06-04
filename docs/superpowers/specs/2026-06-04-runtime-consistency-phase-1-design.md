# Runtime Consistency Phase 1 Design

## Status

Confirmed for implementation on 2026-06-04.

## Context

The runtime currently has several consistency failures across event delivery,
checkpointing, and restart recovery:

- Event subscriptions are removed by business `instance_id`. Scene instances
  reuse the source instance ID, so unregistering a scene instance can remove
  the world instance subscription as well.
- Agent-scoped events match only `instance_id`, so a scene copy can receive an
  event intended for the world instance with the same ID.
- The automatic checkpoint loop acquires the world lock and then calls a
  checkpoint method that acquires the same non-reentrant lock again.
- World startup recreates YAML declarations before restoring snapshots. This
  overwrites persisted runtime state and makes recovery behavior depend on
  startup order.
- `bindings` exist in the runtime instance model but are omitted from SQLite
  persistence and declaration loading.
- Event replay is called during recovery even though normal runtime events are
  not consistently appended to the event log.

This phase makes the existing architecture internally consistent. Runtime code
behavior is the source of truth where it differs from older design documents.

## Goals

1. Make each EventBus registration independently removable.
2. Ensure agent-scoped events are delivered only to world-scope instances.
3. Prevent automatic checkpoint deadlocks and event-loop blocking.
4. Define deterministic snapshot-first recovery with explicit YAML override
   rules.
5. Persist and restore instance `bindings`.
6. Cover the corrected behavior with focused regression tests.

## Non-Goals

The following work is intentionally excluded from this phase:

- Refactoring the overall world lifecycle.
- Changing scene persistence or scene stop semantics beyond exact EventBus
  unregistration.
- Implementing Supervisor MessageHub routing.
- Implementing or correcting model query APIs.
- Implementing complete event sourcing or event replay.
- Changing business-visible instance IDs.

## EventBus Subscription Design

### Subscription identity

Every successful `EventBus.register()` call returns a unique opaque
subscription ID. The ID identifies one registration, independent of the
subscriber's business `instance_id`.

The EventBus stores each subscriber with:

- subscription ID
- business instance ID
- registration scope
- handler

The subscription ID is the only supported key for removing one registration.
Business instance IDs remain unchanged and continue to identify runtime
entities in events and application logic.

### Registration ownership

`EventTrigger` stores the subscription ID returned by `EventBus.register()`.
When the trigger stops, it unregisters that exact subscription. Stopping a
scene therefore cannot remove subscriptions owned by the corresponding
world-scope instance.

Callers that own multiple registrations must retain and unregister each
subscription separately.

### Delivery scope

Event delivery keeps the current scope model with one correction:

- `scope="broadcast"` continues to deliver to all matching subscribers.
- `scope="world"` continues to deliver according to existing world-scope
  routing.
- `scope="agent"` matches both the target business `instance_id` and a
  subscriber registration scope of `world`.

The additional world-scope requirement prevents same-ID scene copies from
receiving agent-targeted events.

### Compatibility

`EventBus.unregister()` accepts a subscription ID. Existing internal callers
that unregister by business `instance_id` must be migrated in this phase.
Keeping ambiguous unregister-by-instance behavior would preserve the original
failure mode and is not supported.

## Checkpoint Design

### Lock ownership

`checkpoint_world()` remains the single owner of the per-world checkpoint
lock. The automatic checkpoint loop calls it without acquiring that lock
first.

This avoids recursive acquisition of a non-reentrant lock and preserves
serialization between manual and automatic checkpoints.

### Event-loop behavior

SQLite checkpoint work is synchronous. Async checkpoint entry points run the
synchronous checkpoint operation with `asyncio.to_thread()`. The world lock is
acquired and released inside that worker-thread operation.

Failures in the automatic checkpoint loop are logged and do not terminate the
loop. Cancellation still propagates so shutdown can stop the loop promptly.

## Snapshot-First Recovery Design

### Sources of instance data

Recovery combines two sources:

- YAML declaration: identity, model, static configuration, attributes, links,
  and initial defaults.
- Persisted snapshot: last known runtime state.

YAML remains required to declare which instances belong to a world. A snapshot
does not create an instance that is no longer declared in YAML.

### Merge precedence

For an instance declared in YAML:

1. Load the YAML declaration.
2. Load its persisted snapshot, if one exists.
3. Start from the full YAML declaration and defaults.
4. If a snapshot exists, replace these runtime-owned fields with snapshot
   values:
   - `state`
   - `variables`
   - `bindings`
   - `memory`
   - `audit`
   - `lifecycle_state`
5. Apply explicitly declared YAML `attributes` and `links` over snapshot
   values.
6. Use YAML identity and model fields regardless of snapshot content.

An omitted YAML `attributes` or `links` field does not erase its snapshot
value. An explicitly declared empty value does erase it.

If no snapshot exists, the instance is created from the complete YAML initial
declaration, including `bindings`.

### Startup ordering

World startup must not delete a persisted snapshot before merging it. The
registry loads declarations and snapshots, performs the merge, then registers
the resulting instance in memory.

The merged instance becomes the current persisted snapshot during the normal
checkpoint lifecycle. Startup does not require an immediate extra checkpoint.

### Event replay

Event replay is disabled during world startup in this phase. The current event
log is incomplete because normal event publication does not consistently
append to it. Replaying an incomplete log would produce misleading state.

Existing event-log storage APIs remain unchanged for future event-sourcing
work.

## Bindings Persistence Design

`bindings` are part of an instance's runtime-owned state and follow snapshot
precedence during recovery.

SQLite instance persistence adds a `bindings` JSON column:

- New databases create the column as part of the instances table.
- Existing databases are migrated idempotently by adding the column when it
  is absent.
- Existing rows without bindings load as an empty object.
- Save, get, and list operations serialize and deserialize bindings.

World declaration loading passes YAML `bindings` into newly created instances.

## Error Handling

- Invalid persisted JSON continues to surface through the store's existing
  error path; recovery must not silently invent replacement runtime state.
- A failed automatic checkpoint is logged with world context and retried on
  the next interval.
- Missing snapshots are normal and use YAML initial values.
- Subscription cleanup is idempotent: stopping an already stopped trigger does
  not remove another registration.

## Implementation Boundaries

Expected production files:

- `src/runtime/event_bus.py`
- `src/runtime/triggers/event_trigger.py`
- `src/runtime/state_manager.py`
- `src/runtime/world_registry.py`
- `src/runtime/stores/sqlite_store.py`
- `src/runtime/instance_manager.py` only if required by the recovery merge

Expected focused test files:

- `tests/runtime/test_event_bus.py`
- `tests/runtime/test_world_instance_scene_integration.py`
- `tests/runtime/test_state_manager.py`
- `tests/runtime/test_world_registry_instance_loading.py`
- `tests/runtime/stores/test_sqlite_store.py`

Changes outside these boundaries require a direct dependency on an acceptance
criterion below.

## Acceptance Criteria

1. Two registrations with the same business instance ID receive distinct
   subscription IDs, and removing one leaves the other active.
2. Stopping a scene instance leaves the same-ID world instance responsive to
   its subscribed events.
3. An agent-targeted event is delivered to the matching world-scope instance
   and not to a same-ID scene-scope instance.
4. The automatic checkpoint loop completes a checkpoint without deadlocking.
5. Async checkpoint execution does not block the event loop while SQLite work
   runs.
6. Restart restores snapshot runtime fields while applying updated YAML static
   identity, model, explicitly declared attributes, and explicitly declared
   links.
7. A declaration without a snapshot starts from its complete YAML initial
   values.
8. Bindings survive SQLite save/load, world restart, and snapshot recovery.
9. World startup does not replay the incomplete event log.
10. Existing focused runtime tests continue to pass, except for independently
    documented pre-existing failures outside this phase.

## Follow-Up Priorities

After this phase, the next architecture work should address:

1. World and scene lifecycle correctness, including actual trigger shutdown and
   scene-definition persistence.
2. Supervisor MessageHub routing consistency.
3. Model query API and unsupported trigger configuration validation.
4. Complete event logging semantics before re-enabling replay.
