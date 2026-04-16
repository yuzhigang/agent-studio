# Package Restructure: supervisor / worker / runtime / cli

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `src/runtime/` 中的进程/服务层拆出到 `src/worker/`，将 CLI 统一入口提升到 `src/cli/`，形成 supervisor → worker → runtime 的单向依赖链。

**Architecture:** `src/cli/main.py` 只做 argparse 分发；`src/worker/` 负责进程外壳（CLI 子命令、文件锁、WebSocket 服务器）；`src/runtime/` 保留纯业务核心；`src/supervisor/` 保持独立管理平面。

**Tech Stack:** Python 3.13, pytest

---

### Task 1: Create `src/cli/` and move CLI main entry

**Files:**
- Create: `src/cli/__init__.py`
- Create: `src/cli/main.py`
- Delete: `src/runtime/cli/main.py`

- [ ] **Step 1: Create `src/cli/__init__.py`**

```python
# src/cli/__init__.py
```

- [ ] **Step 2: Move `src/runtime/cli/main.py` to `src/cli/main.py` and update imports**

Use `git mv`:
```bash
git mv src/runtime/cli/main.py src/cli/main.py
```

Then edit `src/cli/main.py` to update imports:
- `from src.runtime.cli.run_command import run_project` → `from src.worker.cli.run_command import run_project`
- `from src.runtime.cli.run_inline import run_inline` → `from src.worker.cli.run_inline import run_inline`
- `from src.supervisor.cli import supervisor_main` (keep as-is, already correct)

Verify the file still contains the existing argparse structure and the `--force-stop-on-shutdown` flag for the `run` subcommand.

- [ ] **Step 3: Run tests to verify parser still works**

Run: `python -c "from src.cli.main import _build_parser; p = _build_parser(); print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/cli/ src/runtime/cli/main.py
git commit -m "refactor: move CLI main entry to src/cli/"
```

---

### Task 2: Move runtime CLI subcommands to `src/worker/cli/`

**Files:**
- Create: `src/worker/cli/__init__.py`
- Create: `src/worker/cli/run_command.py`
- Create: `src/worker/cli/run_inline.py`
- Delete: `src/runtime/cli/__init__.py`
- Delete: `src/runtime/cli/run_command.py`
- Delete: `src/runtime/cli/run_inline.py`

- [ ] **Step 1: Create `src/worker/cli/__init__.py`**

```python
# src/worker/cli/__init__.py
```

- [ ] **Step 2: Use `git mv` to move CLI subcommand files**

```bash
mkdir -p src/worker/cli
git mv src/runtime/cli/run_command.py src/worker/cli/run_command.py
git mv src/runtime/cli/run_inline.py src/worker/cli/run_inline.py
git mv src/runtime/cli/__init__.py src/worker/cli/__init__.py
```

- [ ] **Step 3: Update imports in the moved files**

Replace all occurrences of `from src.runtime.server.` with `from src.worker.server.` in:
- `src/worker/cli/run_command.py`
- `src/worker/cli/run_inline.py`

- [ ] **Step 4: Run a smoke import test**

Run: `python -c "from src.worker.cli.run_command import run_project; from src.worker.cli.run_inline import run_inline; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add src/worker/cli/
git commit -m "refactor: move worker CLI commands to src/worker/cli/"
```

---

### Task 3: Move `locks/` and `server/` from runtime to worker

**Files:**
- Create: `src/worker/locks/__init__.py`
- Create: `src/worker/locks/project_lock.py`
- Create: `src/worker/server/__init__.py`
- Create: `src/worker/server/jsonrpc_ws.py`
- Delete: `src/runtime/locks/__init__.py`
- Delete: `src/runtime/locks/project_lock.py`
- Delete: `src/runtime/server/__init__.py`
- Delete: `src/runtime/server/jsonrpc_ws.py`

- [ ] **Step 1: Use `git mv` to move `locks/` and `server/`**

```bash
mkdir -p src/worker/locks src/worker/server
git mv src/runtime/locks/__init__.py src/worker/locks/__init__.py
git mv src/runtime/locks/project_lock.py src/worker/locks/project_lock.py
git mv src/runtime/server/__init__.py src/worker/server/__init__.py
git mv src/runtime/server/jsonrpc_ws.py src/worker/server/jsonrpc_ws.py
```

- [ ] **Step 2: Verify imports in `src/worker/cli/run_command.py` and `run_inline.py` are valid**

Run: `python -c "from src.worker.server.jsonrpc_ws import JsonRpcWebSocketServer; from src.worker.locks.project_lock import ProjectLock; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/worker/locks/ src/worker/server/
git commit -m "refactor: move locks and server modules to src/worker/"
```

---

### Task 4: Migrate tests for worker modules

**Files:**
- Create: `tests/worker/cli/__init__.py`
- Create: `tests/worker/cli/test_run_command.py`
- Create: `tests/worker/cli/test_run_inline.py`
- Create: `tests/worker/locks/__init__.py`
- Create: `tests/worker/locks/test_project_lock.py`
- Create: `tests/worker/server/__init__.py`
- Create: `tests/worker/server/test_jsonrpc_ws.py`
- Create: `tests/worker/__init__.py`
- Delete: `tests/runtime/cli/`
- Delete: `tests/runtime/locks/`
- Delete: `tests/runtime/server/`

- [ ] **Step 1: Move test files**

Copy existing tests from:
- `tests/runtime/cli/` → `tests/worker/cli/`
- `tests/runtime/locks/` → `tests/worker/locks/`
- `tests/runtime/server/` → `tests/worker/server/`

- [ ] **Step 2: Update imports in copied test files**

Replace any `from src.runtime.cli.` with `from src.worker.cli.` and any `from src.runtime.server.` or `from src.runtime.locks.` with `from src.worker.` equivalents.

- [ ] **Step 3: Run worker tests**

Run: `pytest tests/worker/ -q`
Expected: All tests pass

- [ ] **Step 4: Delete old test directories and commit**

```bash
git rm -r tests/runtime/cli tests/runtime/locks tests/runtime/server
git add tests/worker/
git commit -m "test: migrate worker tests to tests/worker/"
```

---

### Task 5: Move E2E local spawn test to `tests/worker/`

**Files:**
- Create: `tests/worker/test_e2e_local_spawn.py`
- Delete: `tests/runtime/test_e2e_local_spawn.py` (if it still exists under runtime)

- [ ] **Step 1: Check if `tests/runtime/test_e2e_local_spawn.py` exists**

Run: `ls tests/runtime/test_e2e_local_spawn.py 2>/dev/null || echo "not found"`

- [ ] **Step 2: If it exists, move it**

Copy the file to `tests/worker/test_e2e_local_spawn.py` and update any imports referencing `src.runtime.cli` to `src.cli` or `src.worker.cli`.

- [ ] **Step 3: Run the E2E test**

Run: `pytest tests/worker/test_e2e_local_spawn.py -q`
Expected: PASS

- [ ] **Step 4: Delete old file and commit**

```bash
git rm tests/runtime/test_e2e_local_spawn.py
git add tests/worker/test_e2e_local_spawn.py
git commit -m "test: move e2e local spawn test to tests/worker/"
```

---

### Task 6: Verify full test suite and fix any broken imports

**Files:**
- Potentially modify any file with stale imports

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -q`
Expected: All tests pass (or identify failures due to stale imports)

- [ ] **Step 2: Fix any remaining broken imports across the codebase**

Use grep to find stale references:

```bash
grep -rE "src\.runtime\.(cli|server|locks)" src/ tests/ || true
```

Fix any matches by updating to the new paths (`src.cli`, `src.worker.cli`, `src.worker.server`, `src.worker.locks`). Also watch for relative imports like `from ...runtime.cli` or `import src.runtime.cli`.

- [ ] **Step 3: Run full test suite again**

Run: `pytest tests/ -q`
Expected: All tests pass

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix: update remaining imports after package restructure"
```

---

### Task 7: Update old design spec with new package structure

**Files:**
- Modify: `docs/superpowers/specs/2026-04-16-project-runtime-worker-design.md`

- [ ] **Step 1: Update Section 10 "与现有代码的兼容性"**

Replace the package structure bullet with:

```markdown
- 新增模块按职责拆分为四个顶层包：
  - **`src/cli/`**：统一 CLI 入口。`main.py` 负责 argparse 分发，委托给 `src.supervisor.cli` 和 `src.worker.cli`。
  - **`src/worker/`**：运行时进程外壳。包含 `cli/run_command.py`、`cli/run_inline.py`、`locks/project_lock.py`、`server/jsonrpc_ws.py`。负责把 `runtime` 组装成可独立运行的 OS 进程。
  - **`src/runtime/`**：业务核心逻辑。包含 `event_bus.py`、`instance_manager.py`、`project_registry.py`、`state_manager.py`、`scene_manager.py`、`stores/`、`lib/` 等。不依赖任何上层包。
  - **`src/supervisor/`**：管理平面逻辑。包含 `cli.py`、`gateway.py`、`server.py`。内部严禁导入 `worker` 或 `runtime` 的模块，仅通过 `shutil.which("agent-studio")` 调用 CLI 入口。
```

- [ ] **Step 2: Add new design decision after decision 9**

Append:

```markdown
### 决策 10：将 runtime 拆分为 worker（进程外壳）和 runtime（业务核心）
- **原因**：`runtime` 一词身兼两义，导致包内同时存在"进程生命周期/网络协议"和"业务规则/数据模型"两类代码。把进程外壳提升为独立的 `worker` 包，能让"supervisor 管理 worker → worker 加载 runtime → runtime 执行业务逻辑"的依赖链成为显式的单向结构。
- **收益**：语义清晰；`supervisor` 对 `runtime` 内部完全不可见；`worker` 的进程模型可独立演进。
```

- [ ] **Step 3: Commit spec update**

```bash
git add docs/superpowers/specs/2026-04-16-project-runtime-worker-design.md
git commit -m "docs: update runtime spec with new package structure"
```

---

### Task 8: Final verification

- [ ] **Step 1: Run full test suite one last time**

Run: `pytest tests/ -q`
Expected: All tests pass

- [ ] **Step 2: Verify no stale `src/runtime/cli`, `server`, or `locks` references remain**

Run:
```bash
grep -rE "src\.runtime\.(cli|server|locks)" src/ tests/ || echo "none"
```
Expected: Prints `none`

- [ ] **Step 3: Commit any last-minute fixes**

If needed:
```bash
git add -A && git commit -m "fix: final import cleanup"
```
