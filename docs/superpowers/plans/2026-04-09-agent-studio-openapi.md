# Agent Studio OpenAPI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a complete OpenAPI 3.0 specification (`openapi.json`) at the project root that defines REST endpoints for Agent Studio core resources.

**Architecture:** Produce a single static OpenAPI JSON file derived directly from `model.json`, `ladle_001.json`, and the approved design spec. No server code is required — the output is the spec itself.

**Tech Stack:** JSON / OpenAPI 3.0, Python for validation smoke tests.

---

## Task 1: Generate openapi.json

**Files:**
- Create: `openapi.json`

**Context to embed:**
- Base URL: `https://api.agent-studio.io/v1`
- Tags: Models, Instances, Variables, Services, State Machine, Events, Alarms
- Reusable schemas: `Pagination`, `Error`, `Model`, `ModelInput`, `Instance`, `InstanceInput`, `Variable`, `VariableInput`, `ServiceInvocation`, `State`, `TransitionRequest`, `TransitionResponse`, `Event`, `Alarm`, `AlarmActionResponse`
- Security scheme: `bearerAuth` (HTTP Bearer token, placeholder)

**Endpoints to define:**
- `GET /models`, `POST /models`, `GET /models/{modelId}`, `PUT /models/{modelId}`, `DELETE /models/{modelId}`
- `GET /instances`, `POST /instances`, `GET /instances/{instanceId}`, `PUT /instances/{instanceId}`, `DELETE /instances/{instanceId}`
- `GET /instances/{instanceId}/variables`, `GET /instances/{instanceId}/variables/{name}`, `PUT /instances/{instanceId}/variables/{name}`
- `POST /instances/{instanceId}/services/{serviceName}`
- `GET /instances/{instanceId}/state`, `POST /instances/{instanceId}/transitions`
- `GET /instances/{instanceId}/events`
- `GET /instances/{instanceId}/alarms`, `POST /instances/{instanceId}/alarms/{alarmId}/confirm`, `POST /instances/{instanceId}/alarms/{alarmId}/clear`

**Schema requirements:**
- `Model` / `ModelInput`: must include an embedded `schema` field whose value is the full `model.json` structure.
- `Instance` / `InstanceInput`: `{ id, modelId, state, metadata, attributes, variables, extensions }`, using examples from `ladle_001.json`.
- `Variable`: `{ name, value, valueType, updatedAt }`.
- List responses wrap with `{ data: [...], pagination: {...} }`.
- Errors: `{ error: { code, message, details } }`.

- [ ] **Step 1: Write openapi.json**

Write the complete OpenAPI 3.0 JSON file. Use concrete examples from `model.json` and `ladle_001.json` for schema examples. Ensure all paths, parameters, request bodies, and responses are documented.

- [ ] **Step 2: Validate JSON parseability**

Run:
```bash
python3 -c "import json; data=json.load(open('openapi.json')); print('Valid JSON with', len(data['paths']), 'paths')"
```

Expected output: `Valid JSON with 17 paths` (or close, depending on exact count).

- [ ] **Step 3: Validate OpenAPI structure**

Run:
```bash
python3 -c "
import json
data = json.load(open('openapi.json'))
assert data.get('openapi', '').startswith('3.'), 'Missing/invalid openapi version'
assert 'paths' in data and len(data['paths']) > 0, 'Missing paths'
assert 'components' in data and 'schemas' in data['components'], 'Missing schemas'
assert any(t.get('name') == 'Models' for t in data.get('tags', [])), 'Missing Models tag'
print('OpenAPI structure OK')
"
```

Expected output: `OpenAPI structure OK`

- [ ] **Step 4: Commit**

```bash
git add openapi.json
git commit -m "feat: add OpenAPI 3.0 spec for Agent Studio core resources"
```

---

## Self-Review

**1. Spec coverage:**
- Models CRUD with embedded `schema` ✅
- Instances CRUD + soft delete ✅
- Variables read/write ✅
- Services invocation ✅
- State machine read + trigger transitions ✅
- Events read-only timeline ✅
- Alarms read + confirm/clear ✅
- Pagination and error reusable schemas ✅
- Security placeholder ✅

**2. Placeholder scan:**
- No TBDs or TODOs in the plan. All steps have concrete commands. ✅

**3. Type consistency:**
- Field names match `db-design.md` columns and JSON examples. Path parameters use camelCase (`modelId`, `instanceId`) to align with existing JSON conventions. ✅
