# Agent Studio 前端设计文档

## 1. 项目概述

### 1.1 目标

构建一个纯前端的智能体设计与监控平台，支持：
- **模型设计器**：可视化定义智能体结构（属性、变量、服务、状态机、规则）
- **实例管理**：基于模型创建实例，配置数据绑定
- **运行时模拟**：模拟实例运行，自动执行状态机、调度任务
- **可观测性**：实时查看实例状态、日志、告警和事件

### 1.2 技术栈

- **框架**：React 18 + TypeScript
- **构建工具**：Vite
- **UI组件库**：Ant Design 5
- **样式**：TailwindCSS
- **状态管理**：Zustand
- **路由**：React Router v6
- **状态机可视化**：@antv/g6 或 react-flow

### 1.3 设计原则

1. **单页一体化**：所有核心操作集中在 `/studio` 一个页面，三栏布局
2. **减少跳转**：模型列表 → 实例列表 → 实例详情，同一页面完成
3. **实时反馈**：右侧固定可观测性面板，运行时数据即时可见
4. **Mock优先**：纯前端实现，数据模拟生成，预留后端接口

---

## 2. 目录结构

```
src/
├── pages/                        # 页面层
│   ├── layout.tsx               # 主布局（侧边导航 + 内容区）
│   ├── page.tsx                 # 首页仪表盘
│   ├── studio/                  # 工作室（核心页面）
│   │   ├── page.tsx             # 三栏布局主页面
│   │   ├── layout.tsx           # studio布局
│   │   └── components/          # studio专属组件
│   └── settings/                # 设置页面（预留）
│
├── components/                   # 共享组件
│   ├── layout/                  # 布局组件
│   │   ├── sidebar.tsx          # 侧边导航
│   │   ├── header.tsx           # 顶部栏
│   │   └── breadcrumbs.tsx      # 面包屑
│   ├── model/                   # 模型相关组件
│   │   ├── model-list.tsx       # 模型列表（左栏）
│   │   ├── model-card.tsx       # 模型卡片
│   │   └── model-editor.tsx     # 模型设计器（滑出面板）
│   ├── instance/                # 实例相关组件
│   │   ├── instance-tabs.tsx    # 实例标签页（中栏顶部）
│   │   ├── instance-editor.tsx  # 实例编辑器（中栏主体）
│   │   ├── overview-tab.tsx     # 概览Tab
│   │   ├── variables-tab.tsx    # 变量Tab
│   │   ├── statemachine-tab.tsx # 状态机Tab
│   │   ├── services-tab.tsx     # 服务Tab
│   │   └── config-tab.tsx       # 配置Tab
│   ├── observability/           # 可观测性组件
│   │   ├── observability-panel.tsx  # 右栏面板容器
│   │   ├── status-card.tsx      # 状态卡片
│   │   ├── log-stream.tsx       # 日志流
│   │   ├── alarm-list.tsx       # 告警列表
│   │   ├── event-timeline.tsx   # 事件时间线
│   │   └── metric-chart.tsx     # 指标图表（预留）
│   ├── designer/                # 设计器组件
│   │   ├── property-editor.tsx  # 属性编辑器
│   │   ├── service-editor.tsx   # 服务编辑器
│   │   ├── statemachine-graph.tsx   # 状态机图
│   │   └── rule-editor.tsx      # 规则编辑器
│   └── common/                  # 通用组件
│       ├── json-viewer.tsx      # JSON查看器
│       ├── expression-input.tsx # 表达式输入
│       └── runtime-control.tsx  # 运行控制按钮组
│
├── stores/                       # 状态管理 (Zustand)
│   ├── model-store.ts           # 模型数据
│   ├── instance-store.ts        # 实例数据
│   ├── runtime-store.ts         # 运行时模拟
│   └── monitor-store.ts         # 监控数据
│
├── hooks/                        # 自定义Hooks
│   ├── use-model.ts             # 模型操作
│   ├── use-instance.ts          # 实例操作
│   ├── use-runtime.ts           # 运行时控制
│   └── use-simulation.ts        # 数据模拟
│
├── types/                        # TypeScript类型
│   ├── model.ts                 # 模型类型
│   ├── instance.ts              # 实例类型
│   ├── runtime.ts               # 运行时类型
│   └── monitor.ts               # 监控类型
│
├── utils/                        # 工具函数
│   ├── mock-data.ts             # 模拟数据生成
│   ├── expression-eval.ts       # 表达式计算
│   └── formatters.ts            # 格式化工具
│
├── constants/                    # 常量定义
│   └── ui-config.ts             # UI配置
│
└── styles/                       # 全局样式
    └── globals.css
```

---

## 3. 页面设计

### 3.1 路由结构

| 路由 | 页面 | 说明 |
|------|------|------|
| `/` | 仪表盘 | 统计总览：模型数量、实例数量、运行中实例、活跃告警 |
| `/studio` | 工作室 | **核心页面**，三栏布局：模型列表 + 实例编辑器 + 可观测性面板 |
| `/studio?model=:id` | 工作室（带参数） | 自动选中指定模型 |
| `/studio?instance=:id` | 工作室（带参数） | 自动选中指定实例 |

### 3.2 Studio 页面布局

```
┌─────────────────────────────────────────────────────────────────┐
│  Header: Agent Studio                              [全局搜索] 👤  │
├──────────┬──────────────────────────────────────────────────────┤
│          │  Model Toolbar                                       │
│  Model   │  ┌──────────────────────────────────────────────────┐ │
│  List    │  │ [模型下拉选择 ▼] [+ 新建实例] [编辑模型] [运行 ▶]   │ │
│  (Left)  │  └──────────────────────────────────────────────────┘ │
│          │                                                      │
│  ────────┼──────────────────────────────────────────────────────┤
│          │                                                      │
│  模型A   │  Instance Tabs (Middle-Top)                          │
│  模型B   │  ┌──────────────────────────────────────────────────┐ │
│  模型C   │  │ [实例1] [实例2] [实例3 ▼] [+ 新建] [× 关闭]       │ │
│  ...     │  └──────────────────────────────────────────────────┘ │
│          │                                                      │
│  ────────┤  Instance Editor (Middle)                            │
│          │  ┌──────────────────────────────────────────────────┐ │
│ [+新建]  │  │ Tab: [概览] [变量] [状态机] [服务] [配置]          │ │
│          │  │                                                  │ │
│          │  │ 内容区域根据Tab切换：                              │ │
│          │  │ • 概览：基本信息卡片 + 运行控制 + 快速统计          │ │
│          │  │ • 变量：变量列表 + 绑定配置 + 实时值               │ │
│          │  │ • 状态机：状态图 + 当前状态高亮 + 手动触发         │ │
│          │  │ • 服务：服务列表 + 参数表单 + 执行按钮             │ │
│          │  │ • 配置：实例属性编辑 + 告警规则配置                │ │
│          │  └──────────────────────────────────────────────────┘ │
│          │                                                      │
├──────────┴──────────────────────────┬───────────────────────────┤
│                                     │  Observability Panel      │
│                                     │  (Right - Collapsible)    │
│                                     │  ┌─────────────────────┐  │
│                                     │  │  Status Card        │  │
│                                     │  │  [运行中] [10分钟]   │  │
│                                     │  ├─────────────────────┤  │
│                                     │  │  Log Stream         │  │
│                                     │  │  ▶ [10:23:45] ...   │  │
│                                     │  │  ▶ [10:23:40] ...   │  │
│                                     │  ├─────────────────────┤  │
│                                     │  │  Alarm List (2)     │  │
│                                     │  │  ⚠ 温度过高          │  │
│                                     │  │  ⚠ 容量接近上限      │  │
│                                     │  ├─────────────────────┤  │
│                                     │  │  Event Timeline     │  │
│                                     │  │  ● 状态变更: empty   │  │
│                                     │  │  ● 服务调用: load    │  │
│                                     │  └─────────────────────┘  │
└─────────────────────────────────────┴───────────────────────────┘
```

### 3.3 交互说明

| 操作 | 行为 |
|------|------|
| 点击左栏模型 | 中栏显示该模型的实例列表，默认选中第一个实例 |
| 点击中栏Tab切换 | 切换实例编辑器视图，不丢失其他Tab数据 |
| 点击运行按钮 | 启动运行时模拟，右侧面板开始显示实时数据 |
| 状态机手动触发 | 点击状态节点或转换线，触发状态变更，记录事件 |
| 服务执行 | 填写参数后点击执行，显示结果，记录日志 |
| 右栏折叠 | 点击折叠按钮，右栏收起为图标栏，释放空间 |

---

## 4. 组件设计

### 4.1 ModelList 组件（左栏）

```typescript
interface ModelListProps {
  models: Model[];
  currentModelId: string | null;
  onSelectModel: (modelId: string) => void;
  onEditModel: (modelId: string) => void;
  onCreateModel: () => void;
}
```

**功能**：
- 模型卡片列表，显示名称、描述、实例数量
- 选中高亮
- 右键菜单：编辑 / 复制 / 删除
- 底部新建按钮

### 4.2 InstanceEditor 组件（中栏）

```typescript
interface InstanceEditorProps {
  instance: AgentInstance;
  model: Model;
  onUpdate: (instance: AgentInstance) => void;
  onClose: () => void;
}
```

**Tab内容**：

| Tab | 组件 | 功能 |
|-----|------|------|
| 概览 | `OverviewTab` | 基本信息卡片、运行控制按钮、统计指标 |
| 变量 | `VariablesTab` | 变量表格（名称、类型、绑定、实时值） |
| 状态机 | `StateMachineTab` | 状态机图、当前状态、手动触发控制 |
| 服务 | `ServicesTab` | 服务列表、参数输入、执行按钮、结果展示 |
| 配置 | `ConfigTab` | 实例属性编辑、告警阈值配置 |

### 4.3 ObservabilityPanel 组件（右栏）

```typescript
interface ObservabilityPanelProps {
  instanceId: string;
  collapsed: boolean;
  onToggle: () => void;
}
```

**子组件**：
- `StatusCard`: 显示运行状态、当前状态、运行时长
- `LogStream`: 滚动日志，支持筛选级别（debug/info/warn/error）
- `AlarmList`: 告警列表，支持确认和清除
- `EventTimeline`: 事件时间线，垂直展示

### 4.4 RuntimeControl 组件

```typescript
interface RuntimeControlProps {
  status: 'stopped' | 'running' | 'paused';
  onStart: () => void;
  onPause: () => void;
  onStop: () => void;
  onReset: () => void;
}
```

**功能**：
- 启动/暂停/停止/重置 按钮组
- 运行速度选择（1x / 2x / 5x）
- 模拟数据源选择（随机 / 正弦波 / 阶梯）

### 4.5 StateMachineGraph 组件

```typescript
interface StateMachineGraphProps {
  states: State[];
  transitions: Transition[];
  currentState: string;
  onStateClick?: (state: string) => void;
  onTransitionClick?: (from: string, to: string) => void;
}
```

**功能**：
- 使用 G6 或 react-flow 绘制状态图
- 当前状态节点高亮（绿色边框）
- 状态间连线显示 trigger 条件
- 支持点击手动触发状态转换

---

## 5. 状态管理设计

### 5.1 Model Store

```typescript
interface ModelState {
  models: Model[];
  currentModelId: string | null;
  currentModel: Model | undefined;
  
  // Actions
  setModels: (models: Model[]) => void;
  addModel: (model: Model) => void;
  updateModel: (id: string, updates: Partial<Model>) => void;
  deleteModel: (id: string) => void;
  selectModel: (id: string) => void;
  loadMockModels: () => void;  // 初始化模拟数据
}
```

**持久化**：LocalStorage（`agent-studio-models`）

### 5.2 Instance Store

```typescript
interface InstanceState {
  instances: AgentInstance[];
  currentInstanceId: string | null;
  currentInstance: AgentInstance | undefined;
  
  // Actions
  setInstances: (instances: AgentInstance[]) => void;
  addInstance: (instance: AgentInstance) => void;
  updateInstance: (id: string, updates: Partial<AgentInstance>) => void;
  deleteInstance: (id: string) => void;
  selectInstance: (id: string) => void;
  createFromModel: (modelId: string) => void;
  loadMockInstances: () => void;
}
```

**持久化**：LocalStorage（`agent-studio-instances`）

### 5.3 Runtime Store

```typescript
interface RuntimeState {
  runningInstances: Map<string, RuntimeInstance>;
  simulationSpeed: number;
  
  // Actions
  startInstance: (instanceId: string) => void;
  pauseInstance: (instanceId: string) => void;
  stopInstance: (instanceId: string) => void;
  resetInstance: (instanceId: string) => void;
  setSimulationSpeed: (speed: number) => void;
  
  // 内部方法
  tick: () => void;  // 定时更新
  evaluateRules: (instanceId: string) => void;
  checkStateTransitions: (instanceId: string) => void;
  executeSchedules: (instanceId: string) => void;
}

interface RuntimeInstance {
  instanceId: string;
  status: 'running' | 'paused' | 'stopped';
  currentState: string;
  variables: Record<string, any>;
  startTime: Date;
  lastTick: Date;
}
```

**持久化**：无（运行时数据，刷新重置）

### 5.4 Monitor Store

```typescript
interface MonitorState {
  logs: LogEntry[];
  alarms: Alarm[];
  events: AgentEvent[];
  
  // Actions
  addLog: (log: LogEntry) => void;
  clearLogs: (instanceId?: string) => void;
  addAlarm: (alarm: Alarm) => void;
  acknowledgeAlarm: (alarmId: string) => void;
  recoverAlarm: (alarmId: string) => void;
  addEvent: (event: AgentEvent) => void;
  clearOldData: () => void;  // 清理超过1000条的日志
}

interface LogEntry {
  id: string;
  instanceId: string;
  timestamp: Date;
  level: 'debug' | 'info' | 'warn' | 'error';
  message: string;
  source: 'state-machine' | 'service' | 'schedule' | 'rule' | 'system';
}

interface Alarm {
  id: string;
  instanceId: string;
  ruleId: string;
  severity: 'warning' | 'critical';
  message: string;
  triggeredAt: Date;
  acknowledged: boolean;
  recoveredAt?: Date;
}

interface AgentEvent {
  id: string;
  instanceId: string;
  type: 'state-change' | 'service-call' | 'alarm-trigger' | 'alarm-recover';
  timestamp: Date;
  payload: Record<string, any>;
}
```

**持久化**：无（监控数据，刷新重置）

### 5.5 Store 协作流程

```
用户操作
   │
   ▼
┌─────────────┐    更新    ┌─────────────┐
│ Model Store │ ─────────> │ Instance Store
└─────────────┘            └──────┬──────┘
                                  │
                    选择实例       │
                                  ▼
                         ┌─────────────┐
                         │ Runtime Store│
                         └──────┬──────┘
                                │
            运行时事件（日志/告警/状态变更）
                                │
                                ▼
                         ┌─────────────┐
                         │ Monitor Store│
                         └─────────────┘
```

---

## 6. 数据类型定义

### 6.1 Model 类型（模型定义）

基于 `model.json` 结构：

```typescript
interface Model {
  $schema: string;
  metadata: ModelMetadata;
  attributes: Record<string, AttributeDef>;
  variables: Record<string, VariableDef>;
  derivedProperties: Record<string, DerivedPropertyDef>;
  rules: Record<string, RuleDef>;
  functions: Record<string, FunctionDef>;
  services: Record<string, ServiceDef>;
  states: Record<string, StateDef>;
  transitions: Record<string, TransitionDef>;
  behaviors: Record<string, BehaviorDef>;
  events: Record<string, EventDef>;
  alarms: Record<string, AlarmDef>;
  schedules: Record<string, ScheduleDef>;
}

interface ModelMetadata {
  version: string;
  name: string;
  title: string;
  tags: string[];
  group: string;
  creator: string;
  createdAt: string;
  updatedAt: string;
  description: string;
}

// 各字段详细定义见 types/model.ts
```

### 6.2 AgentInstance 类型（实例）

基于 `ladle_001.json` 结构：

```typescript
interface AgentInstance {
  $schema: string;
  id: string;
  state: string;  // 当前状态
  metadata: InstanceMetadata;
  attributes: Record<string, AttributeValue>;
  variables: Record<string, VariableValue>;
  derivedProperties: Record<string, DerivedPropertyValue>;
  extensions: Extensions;
}

interface InstanceMetadata {
  name: string;
  title: string;
  description: string;
  tags: string[];
  creator: string;
  createdAt: string;
  updatedAt: string;
  kind: string;  // 关联的模型名
  version: string;
}

interface VariableValue {
  title?: string;
  unit?: string;
  description?: string;
  value: any;
  isCustom?: boolean;
  bind?: DataBinding;
}

interface DataBinding {
  source: string;      // 数据源：plc_line_a, mes_system, factory_mqtt
  path?: string;       // OPC UA路径或HTTP路径
  topic?: string;      // MQTT Topic
  selector: string;    // JSON Path选择器
  transform?: string;  // 转换表达式
}

// 详细定义见 types/instance.ts
```

### 6.3 运行时类型

```typescript
interface RuntimeInstance {
  instanceId: string;
  status: 'running' | 'paused' | 'stopped';
  currentState: string;
  variables: Record<string, any>;
  startTime: Date;
  lastTick: Date;
  tickCount: number;
}

interface SimulationConfig {
  speed: number;  // 1, 2, 5
  dataSource: 'random' | 'sine' | 'step' | 'manual';
  interval: number;  // ms
}
```

---

## 7. 模拟数据设计

### 7.1 初始模型数据

预置 `ladle`（钢包）模型，来自 `model.json`。

### 7.2 初始实例数据

预置 `ladle_001` 实例，来自 `ladle_001.json`。

### 7.3 运行时模拟逻辑

```typescript
// 每 tick 执行（根据 speed 调整间隔）
function tick(instanceId: string) {
  const runtime = getRuntime(instanceId);
  const instance = getInstance(instanceId);
  const model = getModel(instance.kind);

  // 1. 更新变量（根据 binding 生成模拟值）
  updateVariables(instance, model);

  // 2. 计算派生属性
  calculateDerivedProperties(instance, model);

  // 3. 评估规则（可能触发告警）
  evaluateRules(instance, model);

  // 4. 检查状态转换条件
  checkTransitions(instance, model, runtime);

  // 5. 执行定时任务
  executeSchedules(instance, model, runtime);

  // 6. 记录日志
  addLog({
    instanceId,
    level: 'debug',
    message: `Tick ${runtime.tickCount} completed`,
    source: 'system'
  });
}
```

### 7.4 模拟数据生成器

```typescript
// 根据变量定义生成模拟值
function generateMockValue(varDef: VariableDef, tick: number, source: string): any {
  switch (source) {
    case 'random':
      return generateRandom(varDef.minimum, varDef.maximum);
    case 'sine':
      return generateSineWave(varDef.minimum, varDef.maximum, tick);
    case 'step':
      return generateStepValue(varDef.minimum, varDef.maximum, tick);
    default:
      return varDef.default;
  }
}
```

---

## 8. 扩展预留

### 8.1 后端接口预留

```typescript
// infrastructure/api/models.ts
// 当前使用 LocalStorage，未来替换为 HTTP API

interface ModelAPI {
  list(): Promise<Model[]>;
  get(id: string): Promise<Model>;
  create(model: Model): Promise<Model>;
  update(id: string, model: Partial<Model>): Promise<Model>;
  delete(id: string): Promise<void>;
}

// 当前实现
const modelAPI: ModelAPI = {
  list: () => Promise.resolve(getFromLocalStorage('models')),
  // ... 其他方法类似
};

// 未来替换
// const modelAPI: ModelAPI = {
//   list: () => axios.get('/api/models'),
//   // ...
// };
```

### 8.2 WebSocket 实时数据预留

```typescript
// infrastructure/websocket/mock.ts
// 当前使用 setInterval 模拟，未来替换为 WebSocket

interface WebSocketClient {
  connect(): void;
  disconnect(): void;
  subscribe(instanceId: string): void;
  unsubscribe(instanceId: string): void;
  onMessage(callback: (data: any) => void): void;
}
```

### 8.3 插件系统预留

```typescript
// 未来支持自定义组件插件
interface Plugin {
  name: string;
  version: string;
  components: Record<string, React.ComponentType>;
  hooks: Record<string, Function>;
}
```

---

## 9. 开发计划

### Phase 1: 基础框架（Week 1）
- [ ] 项目初始化（Vite + React + TS + AntD + Tailwind）
- [ ] 基础布局组件（Header, Sidebar, Layout）
- [ ] 路由配置
- [ ] Store 框架搭建（Zustand）

### Phase 2: 模型管理（Week 1-2）
- [ ] Model Store 实现
- [ ] ModelList 组件（左栏）
- [ ] ModelEditor 组件（滑出面板）
- [ ] PropertyEditor 基础功能

### Phase 3: 实例管理（Week 2）
- [ ] Instance Store 实现
- [ ] InstanceTabs 组件
- [ ] InstanceEditor 框架
- [ ] OverviewTab / ConfigTab

### Phase 4: 运行时模拟（Week 3）
- [ ] Runtime Store 实现
- [ ] 模拟数据生成器
- [ ] RuntimeControl 组件
- [ ] VariablesTab（实时值更新）

### Phase 5: 可观测性（Week 3-4）
- [ ] Monitor Store 实现
- [ ] ObservabilityPanel 组件
- [ ] LogStream / AlarmList / EventTimeline
- [ ] StatusCard

### Phase 6: 状态机可视化（Week 4）
- [ ] StateMachineGraph 组件
- [ ] StateMachineTab 集成
- [ ] 手动状态触发

### Phase 7: 服务与规则（Week 4-5）
- [ ] ServicesTab 实现
- [ ] 服务模拟执行
- [ ] RuleEditor 基础功能

### Phase 8: 优化与测试（Week 5）
- [ ] 性能优化
- [ ] 交互细节打磨
- [ ] Bug修复

---

## 10. 附录

### 10.1 命名规范

- **组件**：PascalCase，如 `ModelList`, `InstanceEditor`
- **Store**：camelCase + Store，如 `useModelStore`, `useRuntimeStore`
- **类型**：PascalCase，如 `Model`, `AgentInstance`, `LogEntry`
- **工具函数**：camelCase，如 `generateMockValue`, `evaluateExpression`

### 10.2 文件模板

```typescript
// 组件模板
import React from 'react';
import { /* AntD components */ } from 'antd';

interface ComponentProps {
  // props定义
}

export const ComponentName: React.FC<ComponentProps> = ({ /* props */ }) => {
  // 实现
};

// Store 模板
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface StoreState {
  // 状态定义
}

export const useStoreName = create<StoreState>()(
  persist(
    (set, get) => ({
      // 初始状态和 actions
    }),
    {
      name: 'store-name',
    }
  )
);
```

---

**文档版本**: 1.0  
**创建日期**: 2026-04-09  
**作者**: Claude Code
