# Agent Model YAML Split Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a `ModelLoader` that supports both directory-based split model configs and legacy single-file `model.yaml`, with full test coverage.

**Architecture:** A simple `ModelLoader` class in `src/runtime/model_loader.py` auto-detects `model/` directory vs legacy `model.yaml`/`model.json`, merges YAML fragments alphabetically, and throws `ModelConfigError` on structural or parse failures.

**Tech Stack:** Python 3.11+, PyYAML, pytest

---

### Task 1: Add PyYAML dependency to pyproject.toml

**Files:**
- Modify: `pyproject.toml:7`

- [ ] **Step 1: Add `pyyaml` to world dependencies**

```toml
dependencies = [
    "watchdog>=3.0.0",
    "pyyaml>=6.0",
]
```

- [ ] **Step 2: Commit**

```bash
git add pyproject.toml
git commit -m "deps: add pyyaml for model yaml loading"
```

---

### Task 2: Create ModelConfigError exception

**Files:**
- Modify: `src/runtime/lib/exceptions.py`
- Test: `tests/runtime/test_model_loader.py` (created in Task 3)

- [ ] **Step 1: Append `ModelConfigError` to exceptions module**

```python
class ModelConfigError(RuntimeError):
    def __init__(self, path: str, details: str = ""):
        self.path = path
        self.details = details
        super().__init__(f"Model config error at {path}: {details}")
```

- [ ] **Step 2: Commit**

```bash
git add src/runtime/lib/exceptions.py
git commit -m "feat: add ModelConfigError for model loading failures"
```

---

### Task 3: Implement legacy single-file loading

**Files:**
- Create: `src/runtime/model_loader.py`
- Create: `tests/runtime/test_model_loader.py`
- Create fixture: `tests/fixtures/agents/legacy_agent/model.yaml`

- [ ] **Step 1: Write failing test for legacy model.yaml loading**

Create `tests/runtime/test_model_loader.py`:

```python
import os
import pytest
from src.runtime.model_loader import ModelLoader, ModelConfigError

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures", "agents")

def test_load_legacy_model_yaml():
    result = ModelLoader.load(os.path.join(FIXTURES, "legacy_agent"))
    assert result["metadata"]["name"] == "legacy_agent"
    assert result["variables"]["temperature"]["default"] == 25.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_model_loader.py::test_load_legacy_model_yaml -v`
Expected: FAIL with "No model configuration found" or import error

- [ ] **Step 3: Create legacy fixture**

Create `tests/fixtures/agents/legacy_agent/model.yaml`:

```yaml
$schema: https://agent-studio.io/schema/v2
metadata:
  name: legacy_agent
  title: Legacy Agent
variables:
  temperature:
    type: number
    default: 25.0
```

- [ ] **Step 4: Implement ModelLoader with legacy support**

Create `src/runtime/model_loader.py`:

```python
import logging
from pathlib import Path
import yaml
from src.runtime.lib.exceptions import ModelConfigError

logger = logging.getLogger(__name__)


class ModelLoader:
    @staticmethod
    def load(agent_path: str | Path) -> dict:
        agent_path = Path(agent_path)
        model_dir = agent_path / "model"

        if model_dir.exists() and model_dir.is_dir():
            return ModelLoader._load_directory(model_dir)

        legacy_yaml = agent_path / "model.yaml"
        if legacy_yaml.exists():
            return ModelLoader._load_yaml_file(legacy_yaml)

        legacy_json = agent_path / "model.json"
        if legacy_json.exists():
            import json
            with open(legacy_json, "r", encoding="utf-8") as f:
                return json.load(f)

        raise ModelConfigError(str(agent_path), "No model configuration found")

    @staticmethod
    def _load_yaml_file(path: Path) -> dict:
        with open(path, "r", encoding="utf-8") as f:
            try:
                data = yaml.safe_load(f)
                return data if data is not None else {}
            except yaml.YAMLError as e:
                raise ModelConfigError(str(path), f"YAML parse error: {e}")

    @staticmethod
    def _load_directory(model_dir: Path) -> dict:
        raise NotImplementedError("Directory mode coming in next task")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/runtime/test_model_loader.py::test_load_legacy_model_yaml -v`
Expected: PASS

- [ ] **Step 6: Write test for legacy model.json loading**

Append to `tests/runtime/test_model_loader.py`:

```python
def test_load_legacy_model_json():
    result = ModelLoader.load(os.path.join(FIXTURES, "legacy_json_agent"))
    assert result["metadata"]["name"] == "legacy_json_agent"
    assert result["attributes"]["power"]["default"] == 100
```

- [ ] **Step 7: Create legacy JSON fixture**

Create `tests/fixtures/agents/legacy_json_agent/model.json`:

```json
{
  "$schema": "https://agent-studio.io/schema/v2",
  "metadata": {
    "name": "legacy_json_agent",
    "title": "Legacy JSON Agent"
  },
  "attributes": {
    "power": {
      "type": "number",
      "default": 100
    }
  }
}
```

- [ ] **Step 8: Run test to verify it passes**

Run: `pytest tests/runtime/test_model_loader.py::test_load_legacy_model_json -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add tests/runtime/test_model_loader.py tests/fixtures/agents/legacy_agent/model.yaml tests/fixtures/agents/legacy_json_agent/model.json src/runtime/model_loader.py
git commit -m "feat: add ModelLoader with legacy model.yaml/json support"
```

---

### Task 4: Implement directory mode loading

**Files:**
- Modify: `src/runtime/model_loader.py`
- Create fixtures: `tests/fixtures/agents/split_agent/model/index.yaml`, `tests/fixtures/agents/split_agent/model/rules.yaml`, `tests/fixtures/agents/split_agent/model/behaviors.yaml`

- [ ] **Step 1: Write failing test for directory mode**

Append to `tests/runtime/test_model_loader.py`:

```python
def test_load_split_model_directory():
    result = ModelLoader.load(os.path.join(FIXTURES, "split_agent"))
    assert result["metadata"]["name"] == "split_agent"
    assert result["variables"]["speed"]["default"] == 10
    assert "capacityLimit" in result["rules"]
    assert "onEnterFull" in result["behaviors"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_model_loader.py::test_load_split_model_directory -v`
Expected: FAIL with "NotImplementedError"

- [ ] **Step 3: Create split agent fixtures**

Create `tests/fixtures/agents/split_agent/model/index.yaml`:

```yaml
$schema: https://agent-studio.io/schema/v2
metadata:
  name: split_agent
  title: Split Agent
attributes:
  maxSpeed:
    type: number
    default: 100
variables:
  speed:
    type: number
    default: 10
states:
  idle:
    title: Idle
```

Create `tests/fixtures/agents/split_agent/model/rules.yaml`:

```yaml
capacityLimit:
  name: capacityLimit
  condition: "this.variables.steelAmount <= this.attributes.capacity"
```

Create `tests/fixtures/agents/split_agent/model/behaviors.yaml`:

```yaml
onEnterFull:
  title: On Enter Full
  trigger:
    type: stateEnter
    state: full
  actions: []
```

- [ ] **Step 4: Implement _load_directory**

Replace `_load_directory` in `src/runtime/model_loader.py`:

```python
    @staticmethod
    def _load_directory(model_dir: Path) -> dict:
        index_file = model_dir / "index.yaml"
        if not index_file.exists():
            raise ModelConfigError(str(model_dir), "Directory mode requires index.yaml")

        base = ModelLoader._load_yaml_file(index_file)
        known_keys = {
            "$schema", "metadata", "attributes", "variables", "derivedProperties",
            "links", "rules", "functions", "services", "states", "transitions",
            "behaviors", "events", "alarms", "schedules", "goals",
            "decisionPolicies", "memory", "plans",
        }

        for yaml_file in sorted(model_dir.glob("*.yaml")):
            if yaml_file.name == "index.yaml":
                continue
            key = yaml_file.stem
            data = ModelLoader._load_yaml_file(yaml_file)
            if data is not None:
                if key not in known_keys:
                    logger.warning("Unknown model key '%s' from file %s", key, yaml_file)
                base[key] = data

        return base
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/runtime/test_model_loader.py::test_load_split_model_directory -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/runtime/model_loader.py tests/fixtures/agents/split_agent/
git add tests/runtime/test_model_loader.py
git commit -m "feat: add directory mode for split model configs"
```

---

### Task 5: Add error handling tests

**Files:**
- Modify: `tests/runtime/test_model_loader.py`
- Create fixture: `tests/fixtures/agents/bad_split_agent/model/.gitkeep` (empty directory to simulate missing index.yaml)

- [ ] **Step 1: Write tests for error cases**

Append to `tests/runtime/test_model_loader.py`:

```python
def test_missing_index_yaml_raises():
    with pytest.raises(ModelConfigError, match="requires index.yaml"):
        ModelLoader.load(os.path.join(FIXTURES, "bad_split_agent"))

def test_missing_model_raises():
    with pytest.raises(ModelConfigError, match="No model configuration found"):
        ModelLoader.load(os.path.join(FIXTURES, "nonexistent_agent"))

def test_invalid_yaml_raises():
    with pytest.raises(ModelConfigError, match="YAML parse error"):
        ModelLoader.load(os.path.join(FIXTURES, "bad_yaml_agent"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/runtime/test_model_loader.py::test_missing_index_yaml_raises tests/runtime/test_model_loader.py::test_missing_model_raises tests/runtime/test_model_loader.py::test_invalid_yaml_raises -v`
Expected: FAIL on missing index and invalid yaml (missing model may already pass)

- [ ] **Step 3: Create error fixtures**

Create `tests/fixtures/agents/bad_split_agent/model/.gitkeep` (empty directory):

```bash
mkdir -p tests/fixtures/agents/bad_split_agent/model
touch tests/fixtures/agents/bad_split_agent/model/.gitkeep
```

Create `tests/fixtures/agents/bad_yaml_agent/model.yaml`:

```yaml
metadata:
  name: bad_yaml_agent
  invalid: [
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/runtime/test_model_loader.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add tests/runtime/test_model_loader.py tests/fixtures/agents/bad_split_agent tests/fixtures/agents/bad_yaml_agent
git commit -m "test: add error handling for model loader"
```

---

### Task 6: Create ladle split model fixture

**Files:**
- Create: `tests/fixtures/agents/logistics/ladle/model/index.yaml`
- Create: `tests/fixtures/agents/logistics/ladle/model/rules.yaml`
- Create: `tests/fixtures/agents/logistics/ladle/model/behaviors.yaml`
- Create: `tests/fixtures/agents/logistics/ladle/model/events.yaml`
- Create: `tests/fixtures/agents/logistics/ladle/model/services.yaml`
- Create: `tests/fixtures/agents/logistics/ladle/model/functions.yaml`
- Create: `tests/fixtures/agents/logistics/ladle/model/alarms.yaml`
- Create: `tests/fixtures/agents/logistics/ladle/model/schedules.yaml`
- Create: `tests/fixtures/agents/logistics/ladle/model/goals.yaml`
- Create: `tests/fixtures/agents/logistics/ladle/model/decisionPolicies.yaml`
- Create: `tests/fixtures/agents/logistics/ladle/model/memory.yaml`
- Create: `tests/fixtures/agents/logistics/ladle/model/plans.yaml`

- [ ] **Step 1: Write integration test for ladle fixture**

Append to `tests/runtime/test_model_loader.py`:

```python
def test_load_ladle_split_model():
    result = ModelLoader.load(os.path.join(FIXTURES, "logistics", "ladle"))
    assert result["metadata"]["name"] == "ladle"
    assert "capacityLimit" in result["rules"]
    assert "onEnterFullSetStatus" in result["behaviors"]
    assert "beginLoad" in result["events"]
    assert "loadSteel" in result["services"]
    assert "calculateLoad" in result["functions"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_model_loader.py::test_load_ladle_split_model -v`
Expected: FAIL (files don't exist yet)

- [ ] **Step 3: Split the real ladle model into fixtures**

Verify that `agents/logistics/ladle/model.yaml` exists; if not, use `agents/logistics/ladle/model.json` as the source. Read the source file and split it into the fixture directory. Use a script or manual split to create the 12+ files. Key contents:

- `index.yaml`: `$schema`, `metadata`, `attributes`, `variables`, `derivedProperties`, `states`, `transitions`, `links`
- `rules.yaml`: all rules
- `behaviors.yaml`: all behaviors
- `events.yaml`: all events
- `services.yaml`: all services
- `functions.yaml`: all functions
- `alarms.yaml`: all alarms
- `schedules.yaml`: all schedules
- `goals.yaml`: all goals
- `decisionPolicies.yaml`: decisionPolicies
- `memory.yaml`: memory
- `plans.yaml`: plans

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/test_model_loader.py::test_load_ladle_split_model -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/agents/logistics/ladle/model/
git add tests/runtime/test_model_loader.py
git commit -m "test: add split model fixture for ladle agent"
```

---

### Task 7: Final verification

- [ ] **Step 1: Run full test suite for runtime**

Run: `pytest tests/runtime/ -v`
Expected: ALL PASS

- [ ] **Step 2: Commit any remaining changes**

If tests pass and no uncommitted changes remain, no action needed.
