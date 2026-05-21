# Event Simulator Design

## Overview

Event Simulator is an external message source that drives world运转 by injecting events through the standard Channel abstraction. It acts as the "power layer" of the world — providing external input energy that triggers internal state changes.

The simulator runs as an independent process, connects to Supervisor via HTTP, and sends events that flow through the full Channel chain: Simulator -> Supervisor -> Worker WebSocket -> JsonRpcChannel -> MessageHub -> World.

## Architecture

```
+------------------ Event Simulator ------------------+
|  +---------+  +---------+  +---------+             |
|  |Source A |  |Source B |  |Source C |             |
|  |(sensor) |  | (MES)   |  | (ERP)   |             |
|  +----+----+  +----+----+  +----+----+             |
|       +-----------+-----------+                     |
|                   |                                 |
|                   v                                 |
|           Scheduler (asyncio tasks)                 |
|                   |                                 |
|                   v HTTP POST                       |
+-------------------|---------------------------------+
                    |
                    v
+-----------------------------------------------------+
|              Supervisor                             |
|  +---------------------------------------------+    |
|  |  POST /api/worlds/{wid}/events              |    |
|  |  POST /api/worlds/{wid}/events/batch        |    |
|  |  GET  /api/worlds/{wid}/outbox              |    |
|  |  -> validate world exists                   |    |
|  |  -> forward via WebSocket to Worker         |    |
|  +---------------------------------------------+    |
+-----------------------------------------------------+
                    | WebSocket
                    v
+-----------------------------------------------------+
|              Worker (run-inline)                    |
|  +---------------------------------------------+    |
|  |  JsonRpcChannel                             |    |
|  |  -> notify.externalEvent                    |    |
|  |  -> MessageHub.on_inbound()                 |    |
|  |  -> InboxProcessor                          |    |
|  |  -> WorldMessageReceiver.receive()          |    |
|  |  -> EventBus.publish()                      |    |
|  +---------------------------------------------+    |
+-----------------------------------------------------+
```

## Key Principles

1. **Channel Purity**: The simulator never bypasses the Channel abstraction. All messages flow through Supervisor -> Worker WebSocket -> JsonRpcChannel -> MessageHub.
2. **Multi-Source Concurrency**: Multiple SimSources can run in parallel, each generating events independently, testing concurrent message ingestion.
3. **Unidirectional (mostly)**: Events flow inbound (simulator -> world). The `GET /outbox` endpoint provides observability for outbound messages without breaking the unidirectional design.
4. **Business-Meaningful Events**: Events are not random noise; they follow business logic (sensor readings with realistic patterns, production line节拍, etc.).

## Supervisor API Additions

### 1. Single Event Push

```http
POST /api/worlds/{world_id}/events
Content-Type: application/json

{
  "event_type": "tick",
  "payload": {"temperature": 85},
  "source": "simulator.sensor-gateway",
  "scope": "world",
  "target": "sensor-01"
}
```

**Response 200**:
```json
{"status": "queued", "message_id": "uuid"}
```

**Response 404**: World not loaded.
**Response 503**: Worker not connected.

### 2. Batch Event Push

```http
POST /api/worlds/{world_id}/events/batch
Content-Type: application/json

{
  "events": [
    {"event_type": "beat", "payload": {}, "scope": "world"},
    {"event_type": "tick", "payload": {"temperature": 85}, "scope": "world"},
    {"event_type": "tick", "payload": {"temperature": 92}, "scope": "world"}
  ]
}
```

**Response 200**:
```json
{"status": "queued", "count": 3, "message_ids": ["uuid1", "uuid2", "uuid3"]}
```

### 3. Query World Outbox (Debugging)

```http
GET /api/worlds/{world_id}/outbox?limit=50&since=2026-05-12T10:00:00Z
```

**Response 200**:
```json
{
  "items": [
    {
      "message_id": "uuid",
      "event_type": "alert",
      "payload": {"level": "high"},
      "source": "sensor-01",
      "target_world": "demo-world",
      "timestamp": "2026-05-12T10:05:23Z"
    }
  ],
  "total": 1
}
```

**Implementation**: Supervisor sends `messageHub.outbox.query` JSON-RPC request to Worker. Worker queries `SQLiteMessageStore` outbox table and returns results.

## Simulator Internal Design

### Components

```
EventSimulator (main process)
├── ConfigLoader     — parse simulator.yaml
├── Scheduler        — global scheduler, manages Source lifecycles
│   └── one asyncio.Task per Source
├── SimSource A      — event generator
│   ├── EventGenerator  — produce events by rules/scripts
│   └── HttpPoster      — send events to Supervisor via HTTP POST
├── SimSource B
│   └── ...
└── OutboxPoller     — optional, poll GET /outbox to verify responses
```

### Source Configuration (simulator.yaml)

```yaml
# Connection config
supervisor_url: http://localhost:8080

# Source list
sources:
  - name: sensor-gateway
    target_world: demo-world
    schedule:
      - event: beat
        every: 2s
        jitter: 0.1s
      - event: tick
        every: 5s
        payload:
          temperature:
            type: gaussian
            mean: 25
            std: 5
    # Complex logic via Python script
    script: |
      from simulator.scripting import Event, Context

      def on_tick(ctx: Context):
          temp = ctx.gaussian(25, 5)
          if temp > 80 and ctx.get("alerting") is None:
              ctx.set("alerting", True)
              return Event("overheat", {"temperature": temp})
          return Event("tick", {"temperature": temp})
```

### Script Engine

```python
class SimContext:
    """Per-Source execution context with isolated state."""
    def __init__(self):
        self._state = {}
        self._rng = random.Random()

    def gaussian(self, mean, std):
        return self._rng.gauss(mean, std)

    def set(self, key, value):
        self._state[key] = value

    def get(self, key, default=None):
        return self._state.get(key, default)

class Event(NamedTuple):
    event_type: str
    payload: dict
    scope: str = "world"
    target: str | None = None
```

**Security**: Script execution uses a whitelist environment (only `math`, `random`, `datetime` allowed). File and network operations are forbidden.

### CLI Entry

```bash
# Start simulator
agent-studio simulate --config simulator.yaml

# Specify Supervisor
agent-studio simulate --config simulator.yaml --supervisor http://localhost:8080

# Run once (send a batch then exit)
agent-studio simulate --config simulator.yaml --once
```

## Worker-Side Handling

When Worker receives `notify.externalEvent` via WebSocket:

1. `JsonRpcChannel._register_handlers()` invokes `on_external_event`
2. `on_external_event` calls `MessageHub.on_inbound()` with a `MessageEnvelope`
3. `MessageHub.on_inbound()` appends to inbox store (`SQLiteMessageStore`)
4. `InboxProcessor` polls inbox and delivers to `WorldMessageReceiver`
5. `WorldMessageReceiver` calls `EventBus.publish()`
6. World instances handle the event via their state machines and triggers

## Testing Strategy

1. **Unit Tests**: Test `EventGenerator` with various payload functions (gaussian, linear, step)
2. **Integration Tests**: Start Supervisor + Worker + Simulator, verify event flows end-to-end
3. **Script Security Tests**: Ensure forbidden operations raise errors in sandbox
