# Agent Studio Agent Model Reflex-Cortex Implementation Plan

**Goal:** 将当前 Agent Studio 的模型体系从“数字孪生/物模型 + 反应式行为”演进为“智能体优先、配置扁平、兼容演进”的统一 schema，并用仓库中的示例文件、设计文档、数据库设计和接口文档把这条演进路径落地。

**Architecture:** 保持 `model.json` 顶层扁平结构；保留现有 `attributes / variables / rules / services / states / transitions / behaviors / alarms / schedules` 作为具身与 `reflex` 骨架；新增 `goals / decisionPolicies / memory / plans` 作为 `cortex` 能力；通过实例文件拆分 `values` 与 `bindings`，并用验证规则约束模型与实例边界。

**Tech Stack:** JSON, Markdown, JSON Schema 或自定义校验脚本, Python 3 用于结构化校验 smoke tests。

---

## Task 1: 固化 v2 契约与字段语义

**Files:**
- Update: `AGENT.md`
- Create: `schema/agent-model-v2.schema.json`
- Create: `schema/agent-instance-v2.schema.json`

**Contract to encode:**
- 统一抽象以 agent 为核心，物模型是具身部分
- `embodiment / reflex / cortex` 只作为概念分层，不作为配置层级
- 最小必选项：`$schema`、`metadata.name`、`metadata.title`
- 至少存在以下之一：`attributes`、`variables`、`services`、`goals`
- 条件必选项：
  - 有 `derivedProperties` 时，其依赖字段必须存在
  - 有 `transitions` 时，必须有 `states`
  - 有 `decisionPolicies` 时，其引用的 `goals / memory / plans` 必须存在
  - 有 `alarms / behaviors / schedules` 时，其动作引用对象必须存在

- [ ] **Step 1: 更新方法论文档**

将 [`AGENT.md`](/Users/zigzag/Code/AI_Test/agent-studio/AGENT.md) 从“数字孪生智能体方法论”升级为“智能体优先、配置扁平”的方法论文档，补充：
- `goals / decisionPolicies / memory / plans` 的职责
- `rules` 与 `goals` 的边界
- `state` 与 `variables.status` 的边界
- `functions` 纯函数约束

- [ ] **Step 2: 增加 machine-readable schema**

创建：
- `schema/agent-model-v2.schema.json`
- `schema/agent-instance-v2.schema.json`

要求：
- 明确顶层字段集合
- 编码最小必选项和条件必选项
- 对 `bindings`、`memory`、`activeGoals`、`currentPlan` 给出实例层结构约束
- 对无法仅靠 JSON Schema 表达的约束留给后续自定义校验器

- [ ] **Step 3: 校验 schema 文件可解析**

Run:
```bash
python3 -c "import json; json.load(open('schema/agent-model-v2.schema.json')); json.load(open('schema/agent-instance-v2.schema.json')); print('Schema JSON OK')"
```

Expected output: `Schema JSON OK`

---

## Task 2: 迁移示例模型到 hybrid agent 结构

**Files:**
- Update: `model.json`

**Model changes to apply:**
- 保持顶层扁平结构
- 补齐被引用但未定义的属性、变量、规则
- 新增 `goals` 与 `decisionPolicies`
- 视情况增加轻量 `memory` 与 `plans` 定义
- 明确 `services` 是统一动作入口
- 明确 `functions` 无副作用

- [ ] **Step 1: 修复当前模型引用不完整问题**

补齐当前模型中被使用但未正式声明的项，例如：
- 缺失规则：`temperatureNotRisingNaturally`
- 缺失变量：`usageCount`、`targetLocation`
- 缺失属性：`refractoryLife`

并修正命名/语义不一致项，例如：
- 将 `temperatureExceeded.warning` 重命名或改触发条件，使名称与实际语义一致

- [ ] **Step 2: 收紧字段职责**

对 `model.json` 做职责校正：
- 将有副作用的 `functions` 调整为纯函数
- 将可复用动作尽量收口到 `services`
- 保证 `states / transitions` 只承担 `reflex` 状态机职责
- 区分实例 `state` 与业务 `status`

- [ ] **Step 3: 为钢包模型增加最小 `cortex`**

在 `model.json` 中增加：
- `goals`
- `decisionPolicies`

建议至少覆盖：
- 安全承载
- 按时送达工位
- 异常场景下允许进入 `cortex`
- `cortex` 不得绕过 `rules`

- [ ] **Step 4: 结构化校验更新后的模型**

Run:
```bash
python3 -c "
import json
data = json.load(open('model.json'))
assert '$schema' in data
assert data['metadata']['name']
assert data['metadata']['title']
assert any(k in data for k in ['attributes', 'variables', 'services', 'goals'])
assert 'goals' in data and 'decisionPolicies' in data
print('model.json structure OK')
"
```

Expected output: `model.json structure OK`

---

## Task 3: 迁移实例示例到运行态结构

**Files:**
- Update: `ladle_001.json`

**Instance changes to apply:**
- 从“定义 + 值 + bind 混合”迁移为“运行值 + bindings + runtime cognition”
- 明确 `modelId`
- 增加 `bindings`
- 视需要增加 `memory`、`activeGoals`、`currentPlan`

- [ ] **Step 1: 清理实例层字段职责**

把实例里的字段定义信息移除，保留实际运行值：
- `attributes.capacity = 200`
- `variables.temperature = 1650`

不要在实例层重复完整字段说明、单位、描述、默认值等模型定义信息。

- [ ] **Step 2: 将 `bind` 抽离为顶层 `bindings`**

将当前内嵌在 `variables.xxx.bind` 中的数据源接线配置迁移到：
- `bindings.temperature`
- `bindings.currentLocation`
- `bindings.usageCount`

保证：
- `variables` 表示内部运行值
- `bindings` 表示外部数据接线方式

- [ ] **Step 3: 增加实例态 `cortex` 运行上下文**

按轻量方式引入：
- `memory`
- `activeGoals`
- `currentPlan`

至少体现：
- 最近异常
- 当前任务目标
- 当前计划摘要

- [ ] **Step 4: 校验更新后的实例结构**

Run:
```bash
python3 -c "
import json
data = json.load(open('ladle_001.json'))
assert data['id']
assert data['modelId']
assert 'variables' in data
assert 'bindings' in data
assert all(not isinstance(v, dict) or 'bind' not in v for v in data['variables'].values())
print('ladle_001.json structure OK')
"
```

Expected output: `ladle_001.json structure OK`

---

## Task 4: 对齐支持性文档与数据契约

**Files:**
- Update: `db-design.md`
- Update: `openapi/models.json`
- Update: `openapi/instances.json`
- Update: `docs/superpowers/specs/2026-04-11-agent-model-reflex-cortex-design.md` if small clarifying deltas are discovered during implementation

**Alignment to perform:**
- 数据库存储设计与 v2 schema 对齐
- OpenAPI 示例与实例形状对齐
- 文档中的必选项、条件必选项与校验器保持一致

- [ ] **Step 1: 更新数据库设计文档**

在 [`db-design.md`](/Users/zigzag/Code/AI_Test/agent-studio/db-design.md) 中明确：
- `bindings` 的存储位置
- `memory / activeGoals / currentPlan` 的存储策略
- `models` 与 `instances` 的 v2 结构约束

优先原则：
- 结构化强查询字段单独成表
- 低频变化的认知上下文优先放 JSON

- [ ] **Step 2: 更新 OpenAPI 示例与 schema 说明**

在 OpenAPI 相关文件中对齐：
- `Model` 示例含 `goals / decisionPolicies`
- `Instance` 示例含 `bindings / memory / activeGoals / currentPlan`
- 变量接口与实例新结构不冲突

- [ ] **Step 3: 做一次文档一致性扫描**

检查以下内容是否一致：
- 顶层字段命名
- 必选项
- `bindings` 所在层级
- `functions` 与 `services` 的职责边界
- `state` 与 `status` 的语义

---

## Task 5: 增加自定义校验与迁移检查

**Files:**
- Create: `scripts/validate_agent_model.py`
- Create: `scripts/validate_agent_instance.py`

**Checks to implement:**
- 引用完整性校验
- 角色边界校验
- 状态机一致性校验
- `cortex` 引用校验
- 模型与实例职责分层校验

- [ ] **Step 1: 实现模型校验脚本**

`scripts/validate_agent_model.py` 至少应覆盖：
- 引用字段存在性
- 状态机合法性
- `functions` 不写状态
- `decisionPolicies` 对 `goals / memory / plans` 的引用完整性

- [ ] **Step 2: 实现实例校验脚本**

`scripts/validate_agent_instance.py` 至少应覆盖：
- 实例必须具备 `id / modelId`
- `variables` 中不得内嵌 `bind`
- `bindings` 仅出现在实例层
- 实例不得重复模型级字段定义元信息

- [ ] **Step 3: 运行校验 smoke tests**

Run:
```bash
python3 scripts/validate_agent_model.py model.json
python3 scripts/validate_agent_instance.py ladle_001.json
```

Expected output:
- `model.json validation passed`
- `ladle_001.json validation passed`

---

## Task 6: 交付与提交

**Files:**
- Update or create all artifacts from Tasks 1-5

- [ ] **Step 1: 最终检查仓库状态**

Run:
```bash
git status --short
```

确认只包含本次实现相关变更。

- [ ] **Step 2: 提交实现**

Run:
```bash
git add AGENT.md schema/ model.json ladle_001.json db-design.md openapi/ scripts/
git commit -m "feat: evolve agent model to reflex-cortex hybrid schema"
```

---

## Self-Review

**1. Plan coverage**
- 概念契约、machine-readable schema、示例模型、示例实例、数据库文档、接口文档、校验脚本都被覆盖。 ✅

**2. Compatibility**
- 计划明确保持顶层扁平结构，不引入 `embodiment / reflex / cortex` 新层级。 ✅

**3. Scope**
- 计划聚焦 schema 演进与示例/文档/校验落地，不扩展到运行引擎实现或 LLM 选型。 ✅

**4. Ambiguity**
- `goals / decisionPolicies` 作为第一阶段必做，`memory / plans` 可轻量引入；迁移顺序和优先级已明确。 ✅
