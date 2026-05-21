# Event Simulator 使用与测试指南

Event Simulator **模拟现实世界的事件和信号**，直接通过 HTTP API 注入 World，驱动 World 的实例模型运行。

它是 World 外部输入的**一种实现方式**（开发/测试阶段的模拟源），不是 World 的感知器本身。World 的感知器（Perceptor）和效应器（Effector）是概念层设计，当前尚未有对应代码。

---

## 目录

- [设计定位](#设计定位)
- [快速开始](#快速开始)
- [YAML 配置详解](#yaml-配置详解)
- [事件生成方式](#事件生成方式)
- [测试指南](#测试指南)
- [模块结构](#模块结构)

---

## 设计定位

### 感知-认知-行动闭环（概念架构）

```
                    ┌─────────────────────────────────────┐
                    │              World                  │
  外部世界 ──→ ┌─────────┐    ┌─────────┐    ┌─────────┐ │
  (传感器、    │Perceptor│───→│EventBus │    │Effector │─┘
   设备、      │(感知器) │    │Instance │───→│(效应器) │──→ 外部世界
   消息队列)   │(概念)   │    │Behavior │    │(概念)   │      (执行器)
               └─────────┘    └─────────┘    └─────────┘
                    ↑                              ↑
            Simulator 直接 HTTP 注入         尚未实现
            （跳过了 Perceptor 层）
```

| 概念 | 状态 | 说明 |
|---|---|---|
| **Perceptor** (感知器) | 概念设计 | World 的输入抽象，任何外部事件源应通过它进入 World |
| **Effector** (效应器) | 概念设计 | World 的输出抽象，World 的决策通过它到达外部执行器 |
| **Simulator** | 已实现 | 模拟现实世界事件的独立进程，**直接 HTTP 注入 World**，当前跳过了 Perceptor 层 |

### Simulator 与真实感知源的对应关系

Simulator 的每个 `source` 模拟一类现实感知源：

| 真实感知源 | Simulator `source` | 典型事件 |
|---|---|---|
| 温度传感器 | `sensor` | `tick` — 带高斯分布的温度值 |
| 心跳监测器 | `heartbeat` | `beat` — 固定间隔的生存信号 |
| 任务调度系统 | `dispatcher` | `dispatchAssigned` — 随机派工指令 |
| 告警系统 | `alert` | `critical` — 指数分布的故障间隔 |

---

## 快速开始

### 启动 Simulator

```bash
# 方式一：使用 Python 模块直接运行
python -m src.simulator.cli simulator.yaml

# 方式二：通过主 CLI（如果已集成）
python -m src.cli.main simulate simulator.yaml
```

启动后会按配置中的 `schedule` 周期性地向指定世界发送事件。按 `Ctrl+C` 优雅停止。

### 配置文件位置

项目根目录已有一份示例配置 [`simulator.yaml`](simulator.yaml)，可直接参考或复制修改。

---

## YAML 配置详解

```yaml
supervisor_url: http://localhost:18080

sources:
  - name: sensor-driver          # 源名称，仅用于日志标识
    target_world: demo-world     # 目标世界 ID
    schedule:
      - event: beat              # 事件类型
        every: 3s                # 发送间隔
        jitter: 500ms            # 随机抖动（可选，默认 0）
        payload: {}              # 事件载荷（可选）
```

### 顶层字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `supervisor_url` | 是 | Supervisor HTTP API 地址 |
| `sources` | 是 | 事件源列表，每个源独立调度 |

### Source 字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `name` | 是 | 源名称，日志中显示 |
| `target_world` | 是 | 事件发往哪个世界 |
| `schedule` | 是 | 定时任务列表 |
| `script` | 否 | Python 脚本路径或内联代码，用于自定义事件生成 |

### Schedule Item 字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `event` | 是 | 事件类型名 |
| `every` | 是 | 间隔时间，支持 `s` / `ms` / `m` |
| `jitter` | 否 | 随机偏移量，实际间隔 = every ± jitter |
| `payload` | 否 | 事件载荷，支持静态值和动态生成规则 |

### Payload 动态生成

在 `payload` 中可以使用以下动态类型：

```yaml
payload:
  temperature:
    type: gaussian      # 高斯分布（正态分布）
    mean: 60            # 均值
    std: 20             # 标准差

  pressure:
    type: uniform       # 均匀分布
    min: 100
    max: 200

  delay:
    type: exponential   # 指数分布
    rate: 0.5           # 速率参数 λ

  load:
    type: triangular    # 三角分布
    low: 0              # 下限
    high: 100           # 上限
    mode: 50            # 众数

  latency:
    type: lognormal     # 对数正态分布
    mu: 0               # ln(X) 的均值
    sigma: 1            # ln(X) 的标准差

  size:
    type: pareto        # 帕累托分布
    alpha: 1.0          # 形状参数

  lifetime:
    type: weibull       # 威布尔分布
    alpha: 1.0          # 尺度参数
    beta: 1.0           # 形状参数

  status:
    value: "normal"     # 静态值（等价于直接写 status: "normal"）
```

每个 source 拥有独立的随机数生成器，动态值按上述分布独立采样。

---

## 事件生成方式

### 方式一：静态 Payload（简单感知信号）

传感器上报固定格式数据，或状态类感知信号：

```yaml
schedule:
  - event: heartbeat
    every: 5s
    payload:
      status: "alive"
```

### 方式二：脚本自定义（复杂感知逻辑）

通过 `script` 字段指定 Python 代码，按事件类型定义处理函数：

```yaml
sources:
  - name: smart-sensor
    target_world: demo-world
    script: |
      def on_tick(ctx):
          temp = ctx.gaussian(60, 20)
          alert = temp > 80
          ctx.set("alerting", alert)
          return Event("tick", {
              "temperature": temp,
              "alert": alert
          })
    schedule:
      - event: tick
        every: 5s
```

脚本规范：

- 函数名格式：`on_<event_name>`，如 `on_tick`、`on_beat`
- 参数 `ctx` 是 [`SimContext`](src/simulator/scripting.py) 实例，提供：
  - `ctx.gaussian(mean, std)` — 高斯分布（正态分布）随机数
  - `ctx.uniform(a, b)` — 均匀分布随机数
  - `ctx.randint(a, b)` — 整数均匀随机数
  - `ctx.exponential(rate)` — 指数分布随机数
  - `ctx.triangular(low, high, mode)` — 三角分布随机数
  - `ctx.lognormal(mu, sigma)` — 对数正态分布随机数
  - `ctx.pareto(alpha)` — 帕累托分布随机数
  - `ctx.weibull(alpha, beta)` — 威布尔分布随机数
  - `ctx.set(key, value)` / `ctx.get(key, default)` — 状态存取
- 返回值：[`Event`](src/simulator/scripting.py) 对象，或 `None`（不发送）
- 沙箱限制：只能导入 `math`, `random`, `datetime`, `json`, `collections` 模块

---

## 炼钢车间完整示例

这是一个复杂工业场景的完整实现：2BOF + 2LF + 1VD + 2CC + 12Ladle，含钢种分流和拉速波动。

### World 结构

```
worlds/steel-plant-01/
├── world.yaml
├── scenes/default.yaml
└── agents/steel/
    ├── bof/model/index.yaml          # 转炉模型
    ├── bof/instances/BOF{1,2}.instance.yaml
    ├── lf/model/index.yaml           # 精炼模型
    ├── lf/instances/LF{1,2}.instance.yaml
    ├── vd/model/index.yaml           # 真空脱气模型
    ├── vd/instances/VD1.instance.yaml
    ├── cc/model/index.yaml           # 连铸模型
    ├── cc/instances/CC{1,2}.instance.yaml
    └── ladle/model/index.yaml        # 钢包模型
        └── instances/L{01..12}.instance.yaml
```

### 设备模型状态机

| 设备 | 状态 | 触发事件 |
|---|---|---|
| **BOF** | `idle` → `charging` → `blowing` → `tapping` → `idle` | `bof.charge.start/end`, `bof.tap.start/end` |
| **LF** | `idle` → `heating` → `idle` | `lf.refine.start/end` |
| **VD** | `idle` → `degassing` → `idle` | `vd.process.start/end` |
| **CC** | `idle` → `casting` → `idle` | `cc.cast.start/end`, `cc.pullspeed.change` |
| **Ladle** | `idle` → `filled` → `at_lf` → `at_vd` → `at_cc` → `idle` | `ladle.{bof,lf,vd,cc}.arrive/leave` |

### 工艺路径

```
普钢(70%):  BOF → LF → CC
优钢(30%):  BOF → LF → VD → CC
```

### 事件命名规范

`设备类型.动作.事件`，三段式：

| 事件 | 说明 |
|---|---|
| `bof.charge.start` / `bof.charge.end` | 转炉兑铁开始/结束 |
| `bof.tap.start` / `bof.tap.end` | 转炉出钢开始/结束 |
| `lf.refine.start` / `lf.refine.end` | LF精炼开始/结束 |
| `vd.process.start` / `vd.process.end` | VD脱气开始/结束 |
| `cc.cast.start` / `cc.cast.end` | 连铸开浇/停浇 |
| `cc.pullspeed.change` | 拉速变化（高斯分布） |
| `ladle.bof.arrive` / `ladle.bof.leave` | 钢包到达/离开转炉 |
| `ladle.lf.arrive` / `ladle.lf.leave` | 钢包到达/离开LF |
| `ladle.vd.arrive` / `ladle.vd.leave` | 钢包到达/离开VD |
| `ladle.cc.arrive` / `ladle.cc.leave` | 钢包到达/离开CC |

### Simulator 配置要点

使用**综合脚本**维护全局事件队列，每 tick（1s）发送一个事件：

```yaml
sources:
  - name: steel-scheduler
    target_world: steel-plant-01
    script: |
      import json
      import random
      def on_tick(ctx):
          # 维护事件队列，按时间顺序出队
          # BOF1/BOF2 各每45s(±5)开始一炉
          # 工序时长：均匀分布模拟波动
          # 钢种：random.random() < 0.3 为优钢
          # 拉速：ctx.gaussian(1.2, 0.05)
          ...
    schedule:
      - event: tick
        every: 1s
```

**关键设计**：
- 1 tick = 1 模拟分钟（加速运行）
- `ctx` 持久化事件队列（`q`）、炉次计数（`heat`）、BOF 调度时间（`bof1_next`/`bof2_next`）
- 每炉生成完整事件序列（20+ 个事件），按时间排序入队
- 钢包简单轮询分配（`L{(heat % 12) + 1:02d}`）

### 启动

```bash
# 启动 world（需要先启动 supervisor）
python -m src.cli.main run --base-dir worlds

# 启动 simulator
python -m src.simulator.cli simulator-steel-plant.yaml
```

---

## 测试指南

### 运行测试

```bash
# 运行所有 simulator 测试
pytest tests/simulator/ -v

# 运行单个测试文件
pytest tests/simulator/test_config.py -v
pytest tests/simulator/test_engine.py -v
pytest tests/simulator/test_scripting.py -v

# 运行单个测试用例
pytest tests/simulator/test_config.py::test_parse_duration -v
```

### 测试结构

| 文件 | 覆盖内容 |
|---|---|
| [`tests/simulator/test_config.py`](tests/simulator/test_config.py) | 配置解析：duration 解析、YAML 加载 |
| [`tests/simulator/test_engine.py`](tests/simulator/test_engine.py) | 引擎生命周期：启动、停止、信号处理 |
| [`tests/simulator/test_scripting.py`](tests/simulator/test_scripting.py) | 脚本执行：上下文状态、事件创建、分布方法、安全限制 |
| [`tests/simulator/test_source.py`](tests/simulator/test_source.py) | 事件生成：各分布类型的 payload 生成 |

### Mock 技巧

Engine 测试使用 `unittest.mock.patch` 隔离 Scheduler：

```python
from unittest.mock import patch, AsyncMock

with patch.object(sim._scheduler, "start", new_callable=AsyncMock) as mock_start:
    await sim.run()
    mock_start.assert_awaited_once()
```

HTTP 相关组件（`HttpPoster`）建议用 `aioresponses` 或 `unittest.mock.AsyncMock` mock：

```python
from unittest.mock import AsyncMock

poster = HttpPoster("http://localhost:8080")
poster._session = AsyncMock()
poster._session.post.return_value.__aenter__.return_value.status = 200
```

### 写新测试用例

#### 1. 测试新的配置格式

```python
def test_load_custom_field(tmp_path):
    config_path = tmp_path / "sim.yaml"
    config_path.write_text("""
supervisor_url: http://localhost:8080
sources:
  - name: sensor
    target_world: demo-world
    schedule:
      - event: beat
        every: 2s
        jitter: 100ms
""")
    cfg = load_config(str(config_path))
    assert cfg.sources[0].schedule[0].jitter == "100ms"
```

#### 2. 测试脚本函数

```python
def test_my_script_logic():
    script = """
def on_tick(ctx):
    ctx.set("count", ctx.get("count", 0) + 1)
    return Event("tick", {"count": ctx.get("count")})
"""
    ctx = SimContext()
    result = run_script(script, "on_tick", ctx)
    assert result.payload["count"] == 1

    # 再次调用验证状态保持
    result = run_script(script, "on_tick", ctx)
    assert result.payload["count"] == 2
```

#### 3. 测试 Source 事件生成

```python
import pytest
from unittest.mock import AsyncMock
from src.simulator.source import SimSource
from src.simulator.config import SourceConfig, ScheduleItem

@pytest.mark.anyio
async def test_source_generates_event():
    poster = AsyncMock()
    cfg = SourceConfig(
        name="test",
        target_world="demo-world",
        schedule=[ScheduleItem(event="beat", every="1s")]
    )
    source = SimSource(cfg, poster)

    # 直接调用内部方法测试事件生成
    item = cfg.schedule[0]
    event = source._generate_event(item)
    assert event.event_type == "beat"
```

### 测试 checklist

添加新功能时，确保覆盖：

- [ ] 配置解析边界值（空列表、缺失字段、异常格式）
- [ ] 脚本沙箱安全性（非法导入、危险操作被阻止）
- [ ] 异步生命周期（start/stop 不会泄漏任务或 session）
- [ ] 动态 payload 分布合理性（值在预期范围内）

---

## 模块结构

```
src/simulator/
├── __init__.py      # 包入口
├── cli.py           # CLI 入口：simulate_main(config_path)
├── config.py        # YAML 配置解析：load_config, _parse_duration
├── engine.py        # 主引擎：EventSimulator（信号处理、生命周期）
├── scheduler.py     # 调度器：Scheduler（管理多个 SimSource）
├── source.py        # 事件源：SimSource（按 schedule 生成事件）
├── poster.py        # HTTP 发送：HttpPoster（发送事件到 Supervisor）
└── scripting.py     # 脚本执行：SimContext, Event, run_script
```

### 数据流

```
simulator.yaml
    ↓
load_config() → SimulatorConfig
    ↓
EventSimulator.run()
    ↓
Scheduler.start() → 为每个 SourceConfig 创建 SimSource
    ↓
SimSource._run() → 按 schedule 循环
    ↓
_generate_event() → Event（静态 payload 或脚本执行）
    ↓
HttpPoster.send() → POST /api/worlds/{world_id}/events
```
