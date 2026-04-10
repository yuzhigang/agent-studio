# Agent Studio 前端实现计划

> **For agentic workers:** REQUIRED: Use @superpowers:subagent-driven-development to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个纯前端的 Agent Studio 平台，包含模型设计器、实例管理、运行时模拟和可观测性面板，采用单页三栏布局。

**Architecture:** 使用 React + TypeScript + Vite 构建，UI 采用 Ant Design 5 + TailwindCSS，状态管理使用 Zustand + persist 中间件实现本地持久化。核心页面为 `/studio`，采用模型列表 | 实例编辑器 | 可观测性面板的三栏布局。

**Tech Stack:** React 18, TypeScript, Vite, Ant Design 5, TailwindCSS, Zustand, React Router v6, @antv/g6

---

## 文件结构

### 将创建的文件

| 文件 | 职责 |
|------|------|
| `src/main.tsx` | 应用入口 |
| `src/App.tsx` | 根组件、路由配置 |
| `src/pages/layout.tsx` | 主布局（Sidebar + Header + 内容区） |
| `src/pages/page.tsx` | 首页/仪表盘 |
| `src/pages/studio/page.tsx` | Studio 核心页面（三栏布局） |
| `src/components/layout/sidebar.tsx` | 侧边导航 |
| `src/components/model/model-list.tsx` | 模型列表（左栏） |
| `src/components/instance/instance-tabs.tsx` | 实例标签页 |
| `src/components/instance/instance-editor.tsx` | 实例编辑器 |
| `src/components/observability/observability-panel.tsx` | 可观测性面板（右栏） |
| `src/stores/model-store.ts` | 模型状态管理 |
| `src/stores/instance-store.ts` | 实例状态管理 |
| `src/stores/runtime-store.ts` | 运行时模拟状态 |
| `src/stores/monitor-store.ts` | 监控数据状态 |
| `src/types/model.ts` | 模型类型定义 |
| `src/types/instance.ts` | 实例类型定义 |
| `src/utils/mock-data.ts` | 模拟数据生成器 |

---

## Task 1: 项目初始化

**Files:**
- Create: `package.json`, `vite.config.ts`, `tsconfig.json`, `index.html`, `src/main.tsx`, `src/App.tsx`, `src/vite-env.d.ts`
- Create: `tailwind.config.js`, `postcss.config.js`, `src/styles/globals.css`

- [ ] **Step 1: 使用 Vite 创建 React + TypeScript 项目**

Run:
```bash
npm create vite@latest . -- --template react-ts
```
Expected: 项目创建成功，显示 `Scaffolding project... Done`

- [ ] **Step 2: 安装依赖**

Run:
```bash
npm install react-router-dom zustand antd @ant-design/icons @antv/g6 immer
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
```
Expected: 所有包安装成功，无报错

- [ ] **Step 3: 配置 TailwindCSS**

Modify: `tailwind.config.js`

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
```

Create: `src/styles/globals.css`

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

body {
  margin: 0;
  padding: 0;
  min-height: 100vh;
}

#root {
  min-height: 100vh;
}
```

- [ ] **Step 4: 配置 Vite 路径别名**

Modify: `vite.config.ts`

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
})
```

Modify: `tsconfig.json` (在 compilerOptions 中添加)

```json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  }
}
```

- [ ] **Step 5: 验证项目能启动**

Run:
```bash
npm run dev
```
Expected: Vite dev server 启动成功，访问 `http://localhost:5173` 显示 Vite + React 默认页面

Kill the dev server after verification.

- [ ] **Step 6: Commit**

```bash
git add .
git commit -m "chore: initialize Vite React TS project with dependencies"
```

---

## Task 2: 类型定义和模拟数据

**Files:**
- Create: `src/types/model.ts`, `src/types/instance.ts`, `src/types/runtime.ts`, `src/types/monitor.ts`
- Create: `src/utils/mock-data.ts`, `src/constants/ui-config.ts`

- [ ] **Step 1: 编写模型类型定义**

Create: `src/types/model.ts`

```typescript
export interface Model {
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

export interface ModelMetadata {
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

export interface AttributeDef {
  type: string;
  title: string;
  description?: string;
  'x-unit'?: string;
  default?: any;
  minimum?: number;
  maximum?: number;
  nullable?: boolean;
}

export interface VariableDef extends AttributeDef {
  'x-rules'?: {
    pre?: RuleRef[];
    post?: RuleRef[];
  };
}

export interface DerivedPropertyDef {
  type: string;
  title: string;
  description?: string;
  'x-unit'?: string;
  'x-formula': string;
  'x-dependOn': string[];
}

export interface RuleRef {
  rule: string;
  parameters?: Record<string, any>;
}

export interface RuleDef {
  name?: string;
  title: string;
  condition: string;
  parameters?: Record<string, ParameterDef>;
  onViolation: {
    action: 'reject' | 'warn';
    error?: { code: string; message: string; suggestion?: string };
    warning?: { code: string; message: string };
  };
}

export interface ParameterDef {
  type: string;
  default?: any;
  description?: string;
}

export interface FunctionDef {
  title: string;
  type: string;
  scriptEngine: string;
  script: string;
  description?: string;
  parameters: Record<string, ParameterDef>;
  returns: Record<string, ParameterDef>;
}

export interface ServiceDef extends FunctionDef {
  rules?: {
    pre?: RuleRef[];
    post?: RuleRef[];
  };
  permissions?: {
    roles: string[];
    description?: string;
  };
}

export interface StateDef {
  title: string;
  description?: string;
  group: string;
  initialState?: boolean;
  actions?: {
    beforeEnter?: Action[];
    afterEnter?: Action[];
    beforeExit?: Action[];
    afterExit?: Action[];
  };
}

export interface TransitionDef {
  title: string;
  from: string;
  to: string;
  priority?: number;
  trigger: Trigger;
  actions?: Action[];
}

export interface BehaviorDef {
  title: string;
  trigger: Trigger;
  actions: Action[];
}

export interface Trigger {
  type: 'event' | 'timeout' | 'condition';
  name?: string;
  when?: string;
  delay?: number;
  condition?: string;
  window?: {
    type: string;
    duration: number;
  };
}

export interface Action {
  type: 'runScript' | 'triggerEvent';
  delay?: number;
  scriptEngine?: string;
  script?: string;
  name?: string;
  payload?: Record<string, any>;
}

export interface EventDef {
  title: string;
  payload: Record<string, ParameterDef>;
}

export interface AlarmDef {
  title: string;
  trigger: Trigger;
  recovery?: Trigger;
  severity: 'warning' | 'critical';
  level: number;
  message: string;
  recoveryMessage?: string;
  schema?: Record<string, any>;
}

export interface ScheduleDef {
  name: string;
  title: string;
  cron: string;
  actions: Action[];
}
```

- [ ] **Step 2: 编写实例类型定义**

Create: `src/types/instance.ts`

```typescript
export interface AgentInstance {
  $schema: string;
  id: string;
  state: string;
  metadata: InstanceMetadata;
  attributes: Record<string, AttributeValue>;
  variables: Record<string, VariableValue>;
  derivedProperties: Record<string, DerivedPropertyValue>;
  extensions: {
    attributes: Record<string, any>;
    variables: Record<string, any>;
    derivedProperties: Record<string, any>;
    functions: Record<string, any>;
    services: Record<string, any>;
    alarms: Record<string, any>;
    behaviors: Record<string, any>;
    schedules: Record<string, any>;
  };
}

export interface InstanceMetadata {
  name: string;
  title: string;
  description: string;
  tags: string[];
  creator: string;
  createdAt: string;
  updatedAt: string;
  kind: string;
  version: string;
}

export interface AttributeValue {
  title?: string;
  unit?: string;
  description?: string;
  value: any;
  isCustom?: boolean;
}

export interface VariableValue extends AttributeValue {
  bind?: DataBinding;
}

export interface DerivedPropertyValue extends AttributeValue {}

export interface DataBinding {
  source: string;
  path?: string;
  topic?: string;
  selector: string;
  transform?: string;
}
```

- [ ] **Step 3: 编写运行时和监控类型定义**

Create: `src/types/runtime.ts`

```typescript
export interface RuntimeInstance {
  instanceId: string;
  status: 'running' | 'paused' | 'stopped';
  currentState: string;
  variables: Record<string, any>;
  startTime: Date;
  lastTick: Date;
  tickCount: number;
}

export interface SimulationConfig {
  speed: number;
  dataSource: 'random' | 'sine' | 'step' | 'manual';
  interval: number;
}
```

Create: `src/types/monitor.ts`

```typescript
export interface LogEntry {
  id: string;
  instanceId: string;
  timestamp: Date;
  level: 'debug' | 'info' | 'warn' | 'error';
  message: string;
  source: 'state-machine' | 'service' | 'schedule' | 'rule' | 'system';
}

export interface Alarm {
  id: string;
  instanceId: string;
  ruleId: string;
  severity: 'warning' | 'critical';
  message: string;
  triggeredAt: Date;
  acknowledged: boolean;
  recoveredAt?: Date;
}

export interface AgentEvent {
  id: string;
  instanceId: string;
  type: 'state-change' | 'service-call' | 'alarm-trigger' | 'alarm-recover' | 'schedule-run';
  timestamp: Date;
  payload: Record<string, any>;
}
```

- [ ] **Step 4: 创建模拟数据文件**

Create: `src/utils/mock-data.ts`

```typescript
import type { Model } from '@/types/model';
import type { AgentInstance } from '@/types/instance';

export const ladleModel: Model = {
  "$schema": "https://agent-studio.io/schema/v1",
  "metadata": {
    "version": "1.0",
    "name": "ladle",
    "title": "钢包智能体",
    "tags": ["logistics", "steelmaking"],
    "group": "logistics",
    "creator": "张三",
    "createdAt": "2024-06-01T10:00:00Z",
    "updatedAt": "2024-06-01T10:00:00Z",
    "description": "钢包智能体，负责盛放和运输钢水"
  },
  "attributes": {
    "capacity": {
      "type": "number",
      "title": "容量",
      "description": "钢包最大容量",
      "x-unit": "ton",
      "default": 200.0,
      "minimum": 0,
      "maximum": 500
    },
    "maxTemperature": {
      "type": "number",
      "title": "最高耐温",
      "description": "钢包能承受的最高温度",
      "x-unit": "℃",
      "default": 1800.0,
      "minimum": 0,
      "maximum": 2000
    },
    "insulationDuration": {
      "type": "number",
      "title": "保温时间",
      "description": "钢水最大保温时长",
      "x-unit": "min",
      "nullable": true,
      "default": 120.0,
      "minimum": 0,
      "maximum": 300
    },
    "refractoryLife": {
      "type": "number",
      "title": "耐材寿命",
      "description": "耐材最大使用次数",
      "x-unit": "次",
      "default": 100,
      "minimum": 0,
      "maximum": 500
    }
  },
  "variables": {
    "steelAmount": {
      "type": "number",
      "title": "钢水量",
      "description": "当前钢包内钢水重量",
      "x-unit": "ton",
      "nullable": true,
      "default": 0.0,
      "minimum": 0,
      "maximum": 500,
      "x-rules": {
        "pre": [{ "rule": "capacityLimit" }]
      }
    },
    "temperature": {
      "type": "number",
      "title": "钢水温度",
      "description": "当前钢水温度",
      "x-unit": "℃",
      "default": 25.0,
      "minimum": -50,
      "maximum": 2000,
      "x-rules": {
        "pre": [{ "rule": "temperatureSafetyRange" }],
        "post": [{ "rule": "temperatureNotRisingNaturally" }]
      }
    },
    "carbonContent": {
      "type": "number",
      "title": "碳含量",
      "description": "钢水中碳元素百分比",
      "x-unit": "%",
      "default": 0.0,
      "minimum": 0,
      "maximum": 2.0
    },
    "steelGrade": {
      "type": "string",
      "title": "钢种",
      "nullable": false,
      "description": "当前钢水的钢种牌号",
      "default": ""
    },
    "currentLocation": {
      "type": "string",
      "title": "当前位置",
      "nullable": true,
      "description": "钢包当前所在位置",
      "default": "standby_area"
    },
    "usageCount": {
      "type": "number",
      "title": "使用次数",
      "description": "耐材已使用次数",
      "x-unit": "次",
      "default": 0,
      "minimum": 0
    }
  },
  "derivedProperties": {
    "fillRate": {
      "type": "number",
      "title": "填充率",
      "description": "钢包填充百分比",
      "x-unit": "%",
      "x-formula": "this.variables.steelAmount / this.attributes.capacity * 100",
      "x-dependOn": ["steelAmount"]
    },
    "remainingCapacity": {
      "type": "number",
      "title": "剩余容量",
      "description": "还可装载的钢水量",
      "x-unit": "ton",
      "x-formula": "this.attributes.capacity - this.variables.steelAmount",
      "x-dependOn": ["steelAmount"]
    }
  },
  "rules": {
    "capacityLimit": {
      "title": "容量上限检查",
      "condition": "this.variables.steelAmount <= this.attributes.capacity",
      "parameters": {
        "limit": { "type": "number", "default": "this.attributes.capacity", "description": "容量上限值" }
      },
      "onViolation": {
        "action": "reject",
        "error": { "code": "CAPACITY_EXCEEDED", "message": "当前钢水量 {steelAmount} 吨超过容量上限 {capacity} 吨" }
      }
    },
    "temperatureSafetyRange": {
      "title": "温度安全范围检查",
      "condition": "this.variables.temperature >= $minTemp && this.variables.temperature <= $maxTemp",
      "parameters": {
        "minTemp": { "type": "number", "default": -50 },
        "maxTemp": { "type": "number", "default": "this.attributes.maxTemperature" }
      },
      "onViolation": {
        "action": "reject",
        "error": { "code": "TEMPERATURE_OUT_OF_RANGE", "message": "温度 {temperature}℃ 超出安全范围 [{$minTemp}, {$maxTemp}]" }
      }
    }
  },
  "functions": {
    "calculateLoad": {
      "title": "计算可装载量",
      "type": "script",
      "scriptEngine": "python",
      "script": "...",
      "description": "计算可装载量",
      "parameters": {
        "weight": { "type": "number", "nullable": false, "description": "请求装载的钢水重量" }
      },
      "returns": {
        "requested": { "type": "number", "description": "请求装载量" },
        "actual": { "type": "number", "description": "实际可装载量" },
        "capacityRemaining": { "type": "number", "description": "装载后剩余容量" }
      }
    }
  },
  "services": {
    "loadSteel": {
      "title": "向钢包装载钢水",
      "type": "script",
      "scriptEngine": "python",
      "rules": {
        "pre": [{ "rule": "refractoryLifeCheck" }, { "rule": "capacityLimit" }]
      },
      "script": "...",
      "parameters": {
        "weight": { "type": "number", "description": "装载钢水重量" },
        "temperature": { "type": "number", "description": "钢水温度" },
        "steelGrade": { "type": "string", "description": "钢种牌号" },
        "carbonContent": { "type": "number", "description": "碳含量百分比" }
      },
      "returns": {
        "success": { "type": "boolean" },
        "message": { "type": "string" },
        "loadedAmount": { "type": "number" },
        "totalAmount": { "type": "number" }
      }
    },
    "pour": {
      "title": "倾倒钢水",
      "type": "script",
      "scriptEngine": "python",
      "rules": {
        "pre": [{ "rule": "hasSteelBeforePour" }, { "rule": "minPourTemperature" }]
      },
      "script": "...",
      "parameters": {},
      "returns": {
        "success": { "type": "boolean" },
        "message": { "type": "string" },
        "pouredAmount": { "type": "number" },
        "location": { "type": "string" }
      }
    },
    "moveTo": {
      "title": "移动钢包到指定位置",
      "type": "script",
      "scriptEngine": "python",
      "rules": {
        "pre": [{ "rule": "highLoadMoveWarning", "parameters": { "threshold": 90 } }]
      },
      "script": "...",
      "parameters": {
        "targetLocation": { "type": "string", "description": "目标位置" }
      },
      "returns": {
        "success": { "type": "boolean" },
        "from": { "type": "string" },
        "to": { "type": "string" }
      }
    }
  },
  "states": {
    "empty": {
      "title": "空包",
      "description": "钢包为空，等待接钢",
      "group": "loadState",
      "initialState": true,
      "actions": {
        "beforeEnter": [{ "type": "runScript", "delay": 0, "scriptEngine": "python", "script": "..." }],
        "afterEnter": [{ "type": "triggerEvent", "name": "ladleStatusChanged", "payload": {} }]
      }
    },
    "receiving": {
      "title": "接钢中",
      "description": "正在接收钢水",
      "group": "loadState",
      "actions": {
        "beforeEnter": [{ "type": "runScript", "delay": 0, "scriptEngine": "python", "script": "..." }],
        "afterEnter": [{ "type": "triggerEvent", "name": "ladleStatusChanged", "payload": {} }]
      }
    },
    "full": {
      "title": "满包",
      "description": "钢包已满，等待运输",
      "group": "loadState",
      "actions": {
        "beforeEnter": [{ "type": "runScript", "delay": 0, "scriptEngine": "python", "script": "..." }],
        "afterEnter": [{ "type": "triggerEvent", "name": "ladleLoaded", "payload": {} }]
      }
    },
    "pouring": {
      "title": "倾倒中",
      "description": "正在倾倒钢水",
      "group": "processState",
      "actions": {
        "beforeEnter": [{ "type": "runScript", "delay": 0, "scriptEngine": "python", "script": "..." }],
        "afterExit": [{ "type": "triggerEvent", "name": "ladleEmptied", "payload": {} }]
      }
    },
    "maintenance": {
      "title": "维护中",
      "description": "钢包正在维护或更换耐材",
      "group": "maintenanceState",
      "actions": {
        "beforeEnter": [{ "type": "runScript", "delay": 0, "scriptEngine": "python", "script": "..." }],
        "beforeExit": [{ "type": "runScript", "delay": 0, "scriptEngine": "python", "script": "..." }]
      }
    }
  },
  "transitions": {
    "emptyToReceiving": {
      "title": "空包转接钢",
      "from": "empty",
      "to": "receiving",
      "trigger": { "type": "event", "name": "beginLoad" }
    },
    "receivingToFull": {
      "title": "接钢转满包",
      "from": "receiving",
      "to": "full",
      "trigger": { "type": "timeout", "delay": 3000 }
    },
    "fullToPouring": {
      "title": "满包转倾倒",
      "from": "full",
      "to": "pouring",
      "priority": 1,
      "trigger": { "type": "event", "name": "beginPour" }
    },
    "pouringToEmpty": {
      "title": "倾倒转空包",
      "from": "pouring",
      "to": "empty",
      "trigger": { "type": "condition", "window": { "type": "time-sliding", "duration": 300 }, "condition": "this.variables.steelAmount <= 0" }
    },
    "maintenanceToEmpty": {
      "title": "维护转空包",
      "from": "maintenance",
      "to": "empty",
      "trigger": { "type": "event", "name": "maintenanceComplete" }
    }
  },
  "behaviors": {},
  "events": {
    "ladleStatusChanged": {
      "title": "钢包状态发生变化",
      "payload": {
        "ladleId": { "type": "string", "description": "钢包ID" },
        "status": { "type": "string", "description": "新状态" },
        "timestamp": { "type": "string", "description": "ISO 8601 时间戳" }
      }
    }
  },
  "alarms": {
    "temperatureExceeded.warning": {
      "title": "温度过高告警",
      "trigger": {
        "type": "condition",
        "window": { "type": "time-sliding", "duration": 300 },
        "condition": "this.variables.temperature > this.attributes.maxTemperature * 0.95"
      },
      "recovery": {
        "type": "condition",
        "window": { "type": "time-sliding", "duration": 300 },
        "condition": "this.variables.temperature <= this.attributes.maxTemperature * 0.95"
      },
      "severity": "warning",
      "level": 1,
      "message": "温度超过阈值 {this.variables.temperature}℃，请检查加热系统",
      "recoveryMessage": "温度已恢复正常，当前温度 {this.variables.temperature}℃，告警已消除"
    }
  },
  "schedules": {
    "checkTemperature": {
      "name": "checkTemperature",
      "title": "定期检查钢水温度",
      "cron": "*/5 * * * *",
      "actions": [{ "type": "runScript", "scriptEngine": "python", "script": "..." }]
    }
  }
};

export const ladleInstance: AgentInstance = {
  "$schema": "https://agent-studio.io/schema/v1",
  "id": "ladle_001",
  "state": "empty",
  "metadata": {
    "name": "ladle",
    "title": "1号钢包",
    "description": "这是一个钢包的数字孪生...",
    "tags": ["steelmaking", "ladle"],
    "creator": "张三",
    "createdAt": "2024-06-01T10:00:00Z",
    "updatedAt": "2024-06-01T10:00:00Z",
    "kind": "ladle",
    "version": "1.0.0"
  },
  "attributes": {
    "capacity": { "title": "容量", "unit": "ton", "description": "钢包最大容量", "value": 200, "isCustom": true },
    "maxTemperature": { "title": "最高耐温", "unit": "℃", "description": "钢包能承受的最高温度", "value": 1800 }
  },
  "variables": {
    "steelAmount": { "title": "钢水量", "unit": "ton", "description": "当前钢包内钢水重量", "value": 0, "isCustom": false, "bind": { "source": "plc_line_a", "path": "ns=2;s=Ladle01.Weight", "selector": "$.value", "transform": "value * 0.001" } },
    "temperature": { "value": 25, "bind": { "source": "plc_line_a", "path": "ns=2;s=Ladle01.Temp", "selector": "$.temperature", "transform": "Math.round(value)" } },
    "carbonContent": { "value": 0.15, "bind": { "source": "mes_system", "path": "/ladles/001/analysis", "selector": "$.chemical.carbon.percent", "transform": "parseFloat(value.toFixed(3))" } },
    "steelGrade": { "value": "Q235B", "bind": { "source": "mes_system", "path": "/ladles/001/grade", "selector": "$.grade.name", "transform": "value.toUpperCase()" } },
    "currentLocation": { "value": "converter_1", "bind": { "source": "factory_mqtt", "topic": "position/ladle/001", "selector": "$.position.zone", "transform": "value.toLowerCase().replace(/\\s/g, '_')" } },
    "usageCount": { "value": 45, "bind": { "source": "mes_system", "path": "/ladles/001/maintenance", "selector": "$.cycles.completed", "transform": "parseInt(value)" } },
    "tiltAngle": { "value": 0, "bind": { "source": "plc_line_a", "path": "ns=2;s=Ladle01.Tilt.Angle", "selector": "$.angle.degrees", "transform": "Math.max(-90, Math.min(90, value))" } },
    "isLidClosed": { "value": true, "bind": { "source": "plc_line_a", "path": "ns=2;s=Ladle01.Lid.Status", "selector": "$.sensors.lidSwitch", "transform": "value === 1 || value === true" } }
  },
  "derivedProperties": {
    "fillRate": { "title": "填充率", "unit": "%", "description": "钢包填充百分比", "value": 0, "isCustom": false },
    "remainingCapacity": { "title": "剩余容量", "unit": "ton", "description": "还可装载的钢水量", "value": 200, "isCustom": false }
  },
  "extensions": {
    "attributes": {},
    "variables": {},
    "derivedProperties": {},
    "functions": {},
    "services": {},
    "alarms": {},
    "behaviors": {},
    "schedules": {}
  }
};
```

**注**：上面 mock-data.ts 中的长字符串脚本内容（如 `"script": "..."`）在实际项目中应该从现有的 `model.json` 和 `ladle_001.json` 复制完整内容。为避免计划文件过长，此处省略。

- [ ] **Step 5: Commit**

```bash
git add src/types src/utils src/constants src/styles
git commit -m "feat: add type definitions and mock data"
```

---

## Task 3: 基础布局和路由

**Files:**
- Create: `src/App.tsx`, `src/pages/layout.tsx`, `src/pages/page.tsx`
- Create: `src/pages/studio/page.tsx`, `src/components/layout/sidebar.tsx`

- [ ] **Step 1: 编写主路由 App.tsx**

Create: `src/App.tsx`

```tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import MainLayout from '@/pages/layout';
import HomePage from '@/pages/page';
import StudioPage from '@/pages/studio/page';

function App() {
  return (
    <ConfigProvider locale={zhCN}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<MainLayout />}>
            <Route index element={<HomePage />} />
            <Route path="studio" element={<StudioPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  );
}

export default App;
```

- [ ] **Step 2: 编写主布局 layout.tsx**

Create: `src/pages/layout.tsx`

```tsx
import { Outlet } from 'react-router-dom';
import { Layout } from 'antd';
import Sidebar from '@/components/layout/sidebar';

const { Header, Content } = Layout;

export default function MainLayout() {
  return (
    <Layout className="min-h-screen">
      <Sidebar />
      <Layout>
        <Header className="bg-white shadow-sm px-6 flex items-center justify-between">
          <h1 className="text-xl font-semibold">Agent Studio</h1>
        </Header>
        <Content className="p-4">
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
```

- [ ] **Step 3: 编写侧边导航 sidebar.tsx**

Create: `src/components/layout/sidebar.tsx`

```tsx
import { useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu } from 'antd';
import {
  HomeOutlined,
  ApartmentOutlined,
} from '@ant-design/icons';

const { Sider } = Layout;

const menuItems = [
  { key: '/', icon: <HomeOutlined />, label: '首页' },
  { key: '/studio', icon: <ApartmentOutlined />, label: '工作室' },
];

export default function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <Sider theme="light" className="shadow-md">
      <div className="h-16 flex items-center justify-center border-b">
        <span className="text-lg font-bold">Agent Studio</span>
      </div>
      <Menu
        mode="inline"
        selectedKeys={[location.pathname]}
        items={menuItems}
        onClick={({ key }) => navigate(key)}
      />
    </Sider>
  );
}
```

- [ ] **Step 4: 创建首页占位 page.tsx**

Create: `src/pages/page.tsx`

```tsx
import { Card, Row, Col, Statistic } from 'antd';

export default function HomePage() {
  return (
    <div className="space-y-4">
      <Row gutter={16}>
        <Col span={6}>
          <Card><Statistic title="模型数量" value={1} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="实例数量" value={1} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="运行中" value={0} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="活跃告警" value={0} /></Card>
        </Col>
      </Row>
    </div>
  );
}
```

- [ ] **Step 5: 创建 Studio 页面框架**

Create: `src/pages/studio/page.tsx`

```tsx
import { useState } from 'react';
import { Row, Col } from 'antd';
import ModelList from '@/components/model/model-list';
import InstanceEditor from '@/components/instance/instance-editor';
import ObservabilityPanel from '@/components/observability/observability-panel';

export default function StudioPage() {
  const [rightCollapsed, setRightCollapsed] = useState(false);

  return (
    <Row gutter={16} className="h-[calc(100vh-112px)]">
      <Col span={4} className="h-full overflow-auto">
        <ModelList />
      </Col>
      <Col span={rightCollapsed ? 20 : 14} className="h-full">
        <InstanceEditor />
      </Col>
      {!rightCollapsed && (
        <Col span={6} className="h-full">
          <ObservabilityPanel onToggle={() => setRightCollapsed(true)} />
        </Col>
      )}
      {rightCollapsed && (
        <Col span={2} className="h-full flex justify-center">
          <button
            onClick={() => setRightCollapsed(false)}
            className="text-blue-500 hover:text-blue-700"
          >
            展开
          </button>
        </Col>
      )}
    </Row>
  );
}
```

- [ ] **Step 6: 启动验证**

Run:
```bash
npm run dev
```

Expected: 
- 访问 `http://localhost:5173` 显示首页仪表盘
- 点击"工作室"进入三栏布局页面（当前是占位内容）
- 点击"首页"返回仪表盘

Kill the dev server after verification.

- [ ] **Step 7: Commit**

```bash
git add src/App.tsx src/pages src/components/layout
git commit -m "feat: add basic layout and routing"
```

---

## Task 4: Model Store 和 Model List 组件

**Files:**
- Create: `src/stores/model-store.ts`
- Create: `src/components/model/model-list.tsx`
- Modify: `src/pages/studio/page.tsx`

- [ ] **Step 1: 编写 Model Store**

Create: `src/stores/model-store.ts`

```typescript
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { Model } from '@/types/model';
import { ladleModel } from '@/utils/mock-data';

interface ModelState {
  models: Model[];
  currentModelId: string | null;
  currentModel: Model | undefined;
  
  setModels: (models: Model[]) => void;
  addModel: (model: Model) => void;
  updateModel: (id: string, updates: Partial<Model>) => void;
  deleteModel: (id: string) => void;
  selectModel: (id: string) => void;
  loadMockModels: () => void;
}

export const useModelStore = create<ModelState>()(
  persist(
    (set, get) => ({
      models: [],
      currentModelId: null,
      get currentModel() {
        return get().models.find(m => m.metadata.name === get().currentModelId);
      },
      setModels: (models) => set({ models }),
      addModel: (model) => set((state) => ({ models: [...state.models, model] })),
      updateModel: (id, updates) => set((state) => ({
        models: state.models.map(m =>
          m.metadata.name === id ? { ...m, ...updates, metadata: { ...m.metadata, ...updates.metadata } } : m
        ),
      })),
      deleteModel: (id) => set((state) => ({
        models: state.models.filter(m => m.metadata.name !== id),
        currentModelId: state.currentModelId === id ? null : state.currentModelId,
      })),
      selectModel: (id) => set({ currentModelId: id }),
      loadMockModels: () => set({ models: [ladleModel], currentModelId: ladleModel.metadata.name }),
    }),
    {
      name: 'agent-studio-models',
      partialize: (state) => ({ models: state.models, currentModelId: state.currentModelId }),
    }
  )
);
```

- [ ] **Step 2: 编写 ModelList 组件**

Create: `src/components/model/model-list.tsx`

```tsx
import { useEffect } from 'react';
import { Card, Button, Empty, Dropdown } from 'antd';
import { PlusOutlined, MoreOutlined } from '@ant-design/icons';
import { useModelStore } from '@/stores/model-store';

export default function ModelList() {
  const { models, currentModelId, loadMockModels, selectModel } = useModelStore();

  useEffect(() => {
    if (models.length === 0) {
      loadMockModels();
    }
  }, [models.length, loadMockModels]);

  return (
    <div className="h-full flex flex-col bg-gray-50 rounded-lg p-3">
      <div className="flex justify-between items-center mb-3">
        <h3 className="font-medium">模型列表</h3>
      </div>
      <div className="flex-1 overflow-auto space-y-2">
        {models.map((model) => (
          <Card
            key={model.metadata.name}
            size="small"
            className={`cursor-pointer ${currentModelId === model.metadata.name ? 'border-blue-500 bg-blue-50' : ''}`}
            onClick={() => selectModel(model.metadata.name)}
            extra={
              <Dropdown
                menu={{
                  items: [
                    { key: 'edit', label: '编辑模型' },
                    { key: 'copy', label: '复制' },
                    { key: 'delete', label: '删除', danger: true },
                  ],
                }}
                trigger={['click']}
              >
                <MoreOutlined onClick={(e) => e.stopPropagation()} />
              </Dropdown>
            }
          >
            <div className="font-medium">{model.metadata.title}</div>
            <div className="text-xs text-gray-500 truncate">{model.metadata.description}</div>
          </Card>
        ))}
        {models.length === 0 && <Empty description="暂无模型" />}
      </div>
      <Button type="dashed" icon={<PlusOutlined />} className="mt-3" block>
        新建模型
      </Button>
    </div>
  );
}
```

- [ ] **Step 3: 启动验证**

Run:
```bash
npm run dev
```

Expected:
- 进入工作室页面后左侧显示"钢包智能体"模型卡片
- 默认选中钢包模型，卡片有蓝色边框

Kill the dev server.

- [ ] **Step 4: Commit**

```bash
git add src/stores/model-store.ts src/components/model/model-list.tsx
git commit -m "feat: add model store and model list component"
```

---

## 后续任务说明

由于 MVP 涉及多个子系统，剩余任务按模块拆分执行：

### Task 5: Instance Store 和实例管理
- `src/stores/instance-store.ts`
- `src/components/instance/instance-tabs.tsx`
- `src/components/instance/instance-editor.tsx`
- `src/components/instance/overview-tab.tsx`
- `src/components/instance/variables-tab.tsx`

### Task 6: Runtime Store 和运行时模拟
- `src/stores/runtime-store.ts`
- `src/components/common/runtime-control.tsx`
- 变量自动更新、状态机转换
- 与 Monitor Store 联动

### Task 7: Monitor Store 和可观测性面板
- `src/stores/monitor-store.ts`
- `src/components/observability/observability-panel.tsx`
- `src/components/observability/status-card.tsx`
- `src/components/observability/log-stream.tsx`
- `src/components/observability/alarm-list.tsx`
- `src/components/observability/event-timeline.tsx`

### Task 8: 状态机可视化
- `src/components/designer/statemachine-graph.tsx`
- `src/components/instance/statemachine-tab.tsx`
- 使用 @antv/g6 绘制状态图

**计划文档已完成，接下来由实现者按照上述 Task 逐步执行。**