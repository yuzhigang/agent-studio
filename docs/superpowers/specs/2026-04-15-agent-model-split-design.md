# Agent Model 配置拆分设计文档

## 1. 背景与目标

当前 `model.yaml`（原 `model.json`）单文件已膨胀至 1200+ 行，20 个顶层配置节全部堆叠在一起，带来两个问题：

1. **阅读和编辑困难**：定位某个规则或行为需要大量滚动。
2. **脚本与配置混杂**：内嵌 DSL/Python 脚本与声明式配置混在一起，视觉上不够清晰。

本设计目标是将过大的 `model.yaml` 拆分为更易于维护的多文件结构，同时：
- 保持向后兼容，不强制废弃 `model.yaml`
- 不改动现有 schema 语义，仅改变物理组织方式
- 内嵌脚本继续保留在 YAML 中，不迁出到外部 `.py` 文件

## 2. 目录结构

以 `agents/logistics/ladle/` 为例，拆分后的结构如下：

```
agents/logistics/ladle/
├── model/                          # 取代原来的 model.yaml
│   ├── index.yaml                  # $schema, metadata, attributes,
│   │                               # variables, derivedProperties,
│   │                               # states, transitions, links
│   ├── rules.yaml
│   ├── functions.yaml
│   ├── services.yaml
│   ├── behaviors.yaml
│   ├── events.yaml
│   ├── alarms.yaml
│   ├── schedules.yaml
│   ├── goals.yaml
│   ├── decisionPolicies.yaml
│   ├── memory.yaml
│   └── plans.yaml
```

### 2.1 分组原则

- **`index.yaml`**：保留相对稳定、体积较小的“结构型”配置节。
  - `$schema`、 `metadata`
  - `attributes`、`variables`、`derivedProperties`
  - `states`、`transitions`、`links`
- **独立文件**：将体积大、变更频繁或逻辑复杂的“行为型”配置节拆出。
  - `rules`、`functions`、`services`
  - `behaviors`、`events`
  - `alarms`、`schedules`
  - `goals`、`decisionPolicies`、`memory`、`plans`

## 3. 加载机制

### 3.1 发现顺序

运行时按以下顺序发现模型配置：

1. 检查 `agents/<group>/<agent>/model/` 目录是否存在。
2. 若存在，按**目录模式**加载。
3. 若不存在，回退读取 legacy `agents/<group>/<agent>/model.yaml`（或 `model.json`）。

### 3.2 合并规则

目录模式下的合并步骤：

1. **加载 `index.yaml`** 作为基础字典 `base`。
2. **按字母顺序遍历目录下其余 `*.yaml` 文件**（不包含子目录）：
   - 以文件名（不含扩展名）作为顶层 key。
   - 将文件内容解析为 dict/list 后，合并到 `base[key]`。
   - 若某文件不存在（如 `alarms.yaml`），则对应的 key 不存在于最终配置中，这是正常行为。
3. 最终得到的字典与单文件 `model.yaml` 的 schema 完全一致。

#### 示例

`rules.yaml` 内容：

```yaml
capacityLimit:
  name: capacityLimit
  ...
temperatureSafetyRange:
  ...
```

合并后等价于原 `model.yaml` 中的：

```yaml
rules:
  capacityLimit:
    ...
  temperatureSafetyRange:
    ...
```

### 3.3 命名规范

文件名直接使用 model schema 中的 camelCase key，无需 snake_case 转换：

- `decisionPolicies.yaml` → 顶层 key `decisionPolicies`
- `derivedProperties.yaml`（如留在目录中）→ 顶层 key `derivedProperties`

## 4. 错误处理

| 场景 | 行为 |
|---|---|
| `index.yaml` 缺失 | 抛出 `ModelConfigError`，提示目录模式下必须包含 `index.yaml` |
| 文件名对应的 key 在 schema 中未知 | 输出警告日志，但**允许通过**，便于未来扩展新配置节 |
| 两个文件映射到同一个 key | 按字母顺序后加载的文件为准（实际应避免重名） |
| YAML 解析失败 | 抛出 `ModelConfigError`，并携带具体文件路径和解析错误信息 |

## 5. 向后兼容

- **Legacy `model.yaml` 继续支持**：现有 agent 无需立即迁移。
- **统一加载入口**：新增 `ModelLoader`（或 `load_model()`），对调用方屏蔽底层是单文件还是目录模式。
- **迁移节奏**：新 agent 推荐直接使用目录模式；旧 agent 可随功能迭代逐步拆分。

## 6. 脚本策略

内嵌 DSL/Python 脚本（存在于 `functions`、`services`、`behaviors`、`schedules` 等节中）**继续保留在 YAML 文件内部**，不迁出到外部 `.py` 文件。原因：

- 这些脚本本质上是配置的一部分，属于“轻量适配层”。
- 脚本语法是受限 DSL，类 Python，但由沙箱执行器解释，不完全等同于标准 Python。
- 将脚本与配置物理分离会引入额外的引用解析复杂度，与“简化阅读”目标相悖。

> 注：项目已有的 `src/runtime/lib/` 方案（`docs/superpowers/specs/2026-04-14-agent-studio-script-lib-design.md`）适用于**复杂业务算法**的外迁。若某 service/behavior 的脚本逻辑过于繁重，可自愿迁到 `agents/<agent>/libs/` 下，再在 YAML 中通过 `lib.xxx()` 调用。这是可选增强，非强制。

## 7. 验收标准

- [ ] 实现 `ModelLoader.load(agent_path)` 同时支持 `model/` 目录和 `model.yaml` 单文件。
- [ ] 目录模式下能正确合并 `index.yaml` 与各分片文件，输出与原单文件等价的配置字典。
- [ ] 对 `index.yaml` 缺失、YAML 解析错误、key 冲突等情况给出清晰的异常信息。
- [ ] 提供至少一个 fixtures 示例（如 `tests/fixtures/agents/logistics/ladle/model/`）。
- [ ] 单元测试覆盖单文件加载、目录加载、错误处理三条路径。
