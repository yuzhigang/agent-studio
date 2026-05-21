# Agent Studio CLI 使用文档

## 安装

```bash
pip install -e .
```

安装后全局可用 `agent-studio` 命令。开发环境也可直接运行源码：

```bash
python -m src.cli.main
```

以下文档统一使用 `agent-studio` 写法，开发时替换为 `python -m src.cli.main` 即可。

---

## 架构说明

Agent Studio 由两个独立的服务组成，分别部署、分别启动：

| 服务 | 作用 | 典型部署位置 |
|---|---|---|
| **Worker** | 加载并运行世界，管理实例生命周期 | 世界运行节点 |
| **Supervisor** | 管理平面，追踪 Worker 注册，暴露 HTTP API | 管理/网关节点 |

---

## Worker 节点命令

在运行世界的机器上执行，需要安装 `agent-studio`。

### run — 启动 Worker 进程

启动一个 Worker 进程，扫描 `--base-dir` 下的所有世界子目录并加载运行。

```bash
agent-studio run --base-dir <path> [options]
```

| 参数 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `--base-dir` | 是 | - | 包含世界子目录的基础目录 |
| `--supervisor-ws` | 否 | `None` | Supervisor WebSocket URL，注册自身到管理平面 |
| `--ws-port` | 否 | `None` | Worker 本地 WebSocket 端口（暴露命令接口） |
| `--force-stop-on-shutdown` | 否 | `None` | 关闭时是否强制停止隔离场景 (`true`/`false`) |

**示例：**

```bash
# 基础启动
agent-studio run --base-dir worlds

# 启动并注册到 Supervisor
agent-studio run \
  --base-dir worlds \
  --supervisor-ws ws://localhost:8001
```

---

### run-inline — 内联运行（开发调试用）

在当前进程内直接运行多个世界，不启动独立 Worker 进程。仅用于本地开发和调试。

```bash
agent-studio run-inline --world-dir <path1> --world-dir <path2> [options]
```

| 参数 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `--world-dir` | 是 | - | 世界目录路径，可重复指定多个 |
| `--supervisor-ws` | 否 | `None` | Supervisor WebSocket URL（可选） |

**示例：**

```bash
agent-studio run-inline \
  --world-dir worlds/demo \
  --world-dir worlds/test
```

---

### sync-models — 同步模型模板

将全局 `agents/` 目录下的模型模板同步到指定世界的私有 `agents/` 中。纯文件操作，不连接任何服务。

> 全局 `agents/` 仅作为模板库。世界首次加载模型时会自动复制。此命令用于后续手动更新已有世界。

```bash
agent-studio sync-models --world-dir <path> [options]
```

| 参数 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `--world-dir` | 是 | - | 目标世界目录 |
| `--force` | 否 | `False` | 强制覆盖冲突文件（不提示） |

**同步行为：**

| 场景 | 行为 |
|---|---|
| 全局有，世界无 | 自动复制到世界 |
| 全局有，世界有 | 冲突时交互式提示（`--force` 直接覆盖） |
| 世界有，全局无 | 世界私有模型，完全跳过 |

**交互式提示：**

```
Conflict: index.yaml. Overwrite? [Y/n/a(ll)/s(kip)]
```

- `Y` / Enter: 覆盖当前文件
- `n`: 跳过当前文件
- `a`: 全部覆盖（后续不再提示）
- `s`: 跳过当前文件

**示例：**

```bash
agent-studio sync-models --world-dir worlds/demo
agent-studio sync-models --world-dir worlds/demo --force
```

---

## Supervisor 节点命令

在运行管理平面的机器上执行，需要安装 `agent-studio`。

### supervisor — 启动 Supervisor 服务

启动 Supervisor 管理平面，接收 Worker 注册并暴露 HTTP API。

```bash
agent-studio supervisor [options]
```

| 参数 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `--base-dir` | 否 | `worlds` | 世界基础目录（用于扫描世界列表） |
| `--ws-port` | 否 | `8001` | Worker 注册 WebSocket 端口 |
| `--http-port` | 否 | `8080` | HTTP API 端口 |

**示例：**

```bash
agent-studio supervisor \
  --base-dir worlds \
  --ws-port 8001 \
  --http-port 8080
```

---

### list-instances — 查询世界实例

查询指定运行中世界的所有实例及其状态。调用 Supervisor HTTP API。

```bash
agent-studio list-instances --world-id <id> [options]
```

| 参数 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `--world-id` | 是 | - | 世界 ID |
| `--supervisor-url` | 否 | `http://localhost:8080` | Supervisor HTTP 地址 |

**输出示例：**

```
Instances in world 'demo':
ID                   Model                Scope      State           Lifecycle
--------------------------------------------------------------------------------
sensor-01            heartbeat            world      idle            active
actor-01             npc                  world      moving          active
```

| HTTP 状态 | 场景 |
|---|---|
| `404` | 世界未在运行 |
| `502` | Worker 返回错误 |
| `504` | Worker 响应超时 |

**示例：**

```bash
# 查询本机 Supervisor
agent-studio list-instances --world-id demo

# 指定远程 Supervisor
agent-studio list-instances \
  --world-id demo \
  --supervisor-url http://192.168.1.10:8080
```

---

## HTTP API 参考

### GET /api/worlds/{world_id}/instances

查询指定运行中世界的所有实例及其状态。

**响应（成功）：**

```json
{
  "instances": [
    {
      "id": "sensor-01",
      "model": "heartbeat",
      "scope": "world",
      "state": "idle",
      "lifecycle_state": "active",
      "variables": {...},
      "attributes": {...}
    }
  ]
}
```

**响应（错误）：**

| HTTP 状态 | 响应体 | 说明 |
|---|---|---|
| `404` | `{"error": "not_running"}` | 世界未在运行 |
| `502` | `{"error": "..."}` | Worker 返回错误 |
| `504` | `{"error": "timeout"}` | Worker 响应超时 |

---

## 典型部署工作流

### 多节点部署

```bash
# ---- Supervisor 节点 ----
agent-studio supervisor \
  --base-dir worlds \
  --ws-port 8001 \
  --http-port 8080

agent-studio list-instances --world-id demo

# ---- Worker 节点 A ----
agent-studio run \
  --base-dir worlds \
  --supervisor-ws ws://supervisor-host:8001

# ---- Worker 节点 B ----
agent-studio run \
  --base-dir worlds \
  --supervisor-ws ws://supervisor-host:8001
```

### 本地开发（单节点）

```bash
# 终端 1: 启动 Supervisor
agent-studio supervisor

# 终端 2: 启动 Worker 并注册
agent-studio run --base-dir worlds --supervisor-ws ws://localhost:8001

# 终端 3: 查询实例
agent-studio list-instances --world-id demo
```

---

## 注意事项

1. **Worker ID 持久化**: Worker 首次运行会在 `{base_dir}/.worker_id` 写入持久化 ID，重启后 Supervisor 将其识别为同一节点
2. **模型加载**: 世界首次引用全局模型时自动复制到世界私有 `agents/`，复制后世界的版本为唯一真相源，不再读取全局模板
3. **Supervisor 通过 Worker 注册发现世界**: Worker 启动后通过 WebSocket 发送 `notify.worker.activated` 消息，汇报自己管理的世界列表。Supervisor 不扫描目录，也不加载世界数据
