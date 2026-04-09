# Agent Studio OpenAPI Design

## Goal
Produce a standard RESTful `openapi.json` for the Agent Studio platform, driven by `model.json`, instance JSON, and `db-design.md`.

## Scope
Focus on core abstractions only:
1. **Models** — metadata & file-backed schema
2. **Instances** — CRUD + soft delete
3. **Variables** — read/write runtime values
4. **Services** — invoke agent-defined services (e.g. `loadSteel`, `pour`)
5. **State Machine** — current state + trigger transitions
6. **Events / Alarms** — read-only event timeline + alarm lifecycle actions

`instance_logs` is excluded (optional and usually external).

## Base URL & Versioning
```
https://api.agent-studio.io/v1
```

## Endpoints

### 1. Models
| Method | Path | Description |
|--------|------|-------------|
| GET | `/models` | List models (paginated) |
| POST | `/models` | Create model |
| GET | `/models/{modelId}` | Get model detail |
| PUT | `/models/{modelId}` | Update model metadata |
| DELETE | `/models/{modelId}` | Delete model |

**Schemas**
- `Model` maps `model.json#metadata` + `filePath`, `groupName`, `isActive`.
- `ModelInput` omits system fields (`createdAt`, `updatedAt`).

### 2. Instances
| Method | Path | Description |
|--------|------|-------------|
| GET | `/instances` | List instances (filter by `modelId`, `state`) |
| POST | `/instances` | Create instance |
| GET | `/instances/{instanceId}` | Get instance (with `attributes` and `variables` inline) |
| PUT | `/instances/{instanceId}` | Update instance metadata / attributes |
| DELETE | `/instances/{instanceId}` | Soft delete |

**Schemas**
- `Instance` maps `ladle_001.json` shape: `id`, `modelId`, `state`, `metadata`, `attributes`, `variables`, `extensions`.
- `InstanceInput` accepts metadata, attributes, and initial variables.

### 3. Variables
| Method | Path | Description |
|--------|------|-------------|
| GET | `/instances/{instanceId}/variables` | Get all variables as flat JSON |
| GET | `/instances/{instanceId}/variables/{name}` | Get single variable |
| PUT | `/instances/{instanceId}/variables/{name}` | Set variable value |

**Schemas**
- Request body: `{"value": <any>, "valueType": "number|string|boolean"}`
- Response body: `{"name": "steelAmount", "value": 150, "valueType": "number", "updatedAt": "..."}`

### 4. Services
| Method | Path | Description |
|--------|------|-------------|
| POST | `/instances/{instanceId}/services/{serviceName}` | Invoke a service |

**Behavior**
- Request body schema is derived **dynamically** from `model.json#services.{serviceName}.parameters`.
- Response body schema is derived from `model.json#services.{serviceName}.returns`.
- OpenAPI will document the common `ServiceInvocationRequest/Response` wrappers, with concrete payloads as `object` (generic) because service definitions vary per model.

### 5. State Machine
| Method | Path | Description |
|--------|------|-------------|
| GET | `/instances/{instanceId}/state` | Current state object |
| POST | `/instances/{instanceId}/transitions` | Trigger a transition by event name |

**Schemas**
- `State`: `{ "currentState": "empty", "availableTransitions": ["emptyToReceiving", ...] }`
- `TransitionRequest`: `{ "event": "beginLoad", "payload": {...} }`
- `TransitionResponse`: `{ "success": true, "from": "empty", "to": "receiving" }`

### 6. Events
| Method | Path | Description |
|--------|------|-------------|
| GET | `/instances/{instanceId}/events` | Read-only event timeline |

**Query params**: `eventType`, `from`, `to`, `limit`, `offset`

**Schema**
- `Event`: `{ "id", "instanceId", "eventType", "timestamp", "payload", "createdAt" }`

### 7. Alarms
| Method | Path | Description |
|--------|------|-------------|
| GET | `/instances/{instanceId}/alarms` | List alarms |
| POST | `/instances/{instanceId}/alarms/{alarmId}/confirm` | Confirm alarm |
| POST | `/instances/{instanceId}/alarms/{alarmId}/clear` | Clear alarm |

**Query params**: `status`, `severity`, `level`

**Schema**
- `Alarm`: `{ "id", "instanceId", "ruleId", "severity", "level", "status", "message", "payload", "triggeredAt", "confirmedAt", "confirmedBy", "clearedAt", "clearedBy" }`

## Common Components

### Pagination
List endpoints use:
```json
{
  "data": [...],
  "pagination": {
    "limit": 20,
    "offset": 0,
    "total": 100
  }
}
```

### Error Response
```json
{
  "error": {
    "code": "CAPACITY_EXCEEDED",
    "message": "...",
    "details": {}
  }
}
```
HTTP status codes: `400`, `401`, `403`, `404`, `409`, `422`, `500`.

## Mapping from Source Files
1. `model.json` → Model metadata, attribute schemas, service parameter/return schemas, state names, transition names, rule names.
2. `ladle_001.json` → Instance JSON shape, `bind` metadata for variables, example values.
3. `db-design.md` → Table columns and relationships (FKs, indexes) inform query parameters and response fields.

## Out of Scope
- Authentication / authorization spec (placeholder security scheme only).
- File upload endpoints for `model.json` (assumed managed externally; `filePath` is stored).
- `instance_logs` (optional table).
