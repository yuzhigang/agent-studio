# World 静态实例声明加载设计

**日期**: 2026-04-18  
**状态**: 草案  

## 背景

当前 Agent Studio 运行时（`WorldRegistry.load_world()`）加载世界后，世界内没有任何实例。用户必须通过代码调用 `InstanceManager.create()` 手动创建实例。这在开发测试阶段可行，但在生产部署时不可接受——每个世界的常驻实例（钢包、天车、调度员等）必须随世界启动自动加载。

本设计引入 **静态实例声明** 机制：在世界目录下通过 `.instance.yaml` 文件声明常驻实例，世界启动时自动加载。

## 核心原则

1. **按生命周期区分，不按类型区分**：`lifecycle: static`（常驻，文件声明）vs `dynamic`（运行时创建）。钢包（Thing）和调度员（Role）都可以是 static；某些 Concept 也可以预置为 static。
2. **目录结构与全局模型对齐**：世界目录下的 `{namespace}/{modelId}/{model|instances}` 结构与全局模型库完全一致，降低心智负担。
3. **世界模型优先**：世界私有模型覆盖全局模型，同名 modelId 优先使用世界目录下的定义。
4. **动态实例不配置**：`dynamic` 实例不在文件系统中存在，运行时通过事件/API/加载器创建。

## 实例文件格式

参照 `ladle_dispatcher.instance.json`，使用完全一致的字段名，仅文件格式为 YAML。

```yaml
# worlds/steel-plant-01/agents/logistics/ladle/instances/ladle-01.instance.yaml
$schema: https://agent-studio.io/schema/v2/instance
id: ladle-01
modelId: ladle

state: empty

metadata:
  name: ladle-01
  title: 钢包 1 号
  description: 一号产线钢包
  version: "1.0"

attributes:
  capacity: 200

variables:
  steelAmount: 0
  temperature: 25
  currentLocation: standby_area

bindings:
  temperature:
    source: plc_line_a
    path: /sensors/temp01
    selector: "$.value"
    transform: value

memory: {}

activeGoals: []
currentPlan: null
extensions: {}
```

### 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `$schema` | 否 | Schema 标识 |
| `id` | 是 | 实例唯一标识 |
| `modelId` | 是 | 模型的唯一标识，如 `ladle`、`crane` |
| `state` | 否 | 初始状态机状态（字符串），如 `empty`、`idle` |
| `metadata` | 否 | 实例元数据 |
| `attributes` | 否 | 覆盖模型默认的属性值 |
| `variables` | 否 | 覆盖模型默认的变量值 |
| `bindings` | 否 | 外部数据源绑定映射，含 `source`、`path`、`selector`、`transform` |
| `memory` | 否 | 初始记忆数据 |
| `activeGoals` | 否 | 当前激活的目标列表 |
| `currentPlan` | 否 | 当前执行中的计划 |
| `extensions` | 否 | 扩展字段 |

## 目录结构

世界根目录下用 `agents/` 隔离所有模型和实例声明，与全局模型库结构对齐：

```
worlds/steel-plant-01/
  world.yaml
  scenes/
    live-view.yaml
  agents/                             ← 世界的 agents 定义
    logistics/
      ladle/
        model/                          ← 世界私有模型定义（覆盖全局）
          index.yaml
          behaviors.yaml
        instances/                      ← 该模型的静态实例声明
          ladle-01.instance.yaml
          ladle-02.instance.yaml
        libs/                           ← 模型专属共享库（可选）
      crane/
        model/
        instances/
          crane-01.instance.yaml
    roles/                              ← 另一命名空间
      master-planner/
        model/
        instances/
          mp-01.instance.yaml
      operator/
        model/
        instances/
          op-day-shift.instance.yaml
  runtime.db
```

全局模型库（优先级低于世界私有模型）：

```
agents/                               ← 全局模型根目录（可配置）
  logistics/
    ladle/
      model/
        index.yaml
        behaviors.yaml
      libs/
  roles/
    master-planner/
      model/
```

## 模型搜索路径

`modelId`（如 `ladle`）通过以下方式解析为模型目录：

### 搜索顺序

1. **世界私有模型优先**：在 `{world_dir}/agents/` 下递归查找目录名等于 `modelId` 且包含 `model/` 子目录的文件夹
2. **全局模型兜底**：在世界私有模型未找到时，在每个全局搜索路径下递归查找

### 搜索示例

```
# modelId = "ladle"
worlds/steel-plant-01/
  agents/                  ← 世界私有 agents
    logistics/
      ladle/
        model/             ← 命中！优先使用
          index.yaml
  ...

agents/                    ← 全局搜索路径
  logistics/
    ladle/
      model/               ← 世界私有已命中，此目录被忽略
```

```
# modelId = "crane"
worlds/steel-plant-01/
  agents/                  ← 世界中无 crane 模型

agents/                    ← 全局搜索路径
  crane/
    model/                 ← 命中
```

### 解析器接口

```python
class ModelResolver:
    def __init__(self, world_dir: str, global_search_paths: list[str]):
        self._world_dir = Path(world_dir)
        self._global_paths = [Path(p) for p in global_search_paths]

    def resolve(self, modelId: str) -> Path | None:
        """返回 model/ 目录的完整路径，未找到返回 None"""
        # 1. 先在世界目录的 agents/ 下搜索
        world_agents = self._world_dir / "agents"
        if world_agents.exists():
            model_dir = self._find_model_dir(world_agents, modelId)
            if model_dir is not None:
                return model_dir
        # 2. 再在全局路径下搜索
        for search_path in self._global_paths:
            model_dir = self._find_model_dir(search_path, modelId)
            if model_dir is not None:
                return model_dir
        return None

    def _find_model_dir(self, root: Path, modelId: str) -> Path | None:
        for candidate in root.rglob(f"*/{modelId}/model"):
            if candidate.is_dir():
                return candidate
        return None
```

## 加载流程

```
WorldRegistry.load_world(world_id)
  ├── 读取 world.yaml
  ├── 初始化 SQLiteStore、EventBusRegistry、InstanceManager、SceneManager...
  ├── 扫描世界目录下的所有 instances/ 子目录（新增）
  │     ├── 递归遍历 */instances/*.instance.yaml
  │     ├── 解析 YAML → InstanceDeclaration
  │     ├── modelId → ModelResolver.resolve(modelId) → model_dir
  │     ├── ModelLoader.load(model_dir) → model dict
  │     ├── 合并模型默认值 + 声明覆盖值
  │     └── InstanceManager.create(
  │             world_id, modelId, id,
  │             model=model,
  │             state=declaration.state,
  │             attributes=merged_attributes,
  │             variables=merged_variables,
  │             memory=declaration.memory,
  │         )
  ├── StateManager.restore_world(world_id)  ← 声明加载完成后执行恢复
  ├── 加载 scenes/
  └── 返回 bundle
```

## 与现有系统的集成点

### 1. InstanceManager 的 model_loader

当前 `InstanceManager.__init__()` 的 `model_loader` 参数为 `None`（未传入）。本设计要求：

- `WorldRegistry.load_world()` 创建 `ModelResolver` 实例
- 将 resolver 作为 `model_loader` 闭包传入 `InstanceManager`：

```python
resolver = ModelResolver(world_dir, global_search_paths)

def model_loader(modelId: str) -> dict | None:
    model_dir = resolver.resolve(modelId)
    if model_dir is not None:
        return ModelLoader.load(model_dir)
    return None

im = InstanceManager(
    bus_reg,
    instance_store=store,
    world_state=world_state,
    model_loader=model_loader,
)
```

这样 `InstanceManager._lazy_load()` 在从数据库恢复实例时也能自动加载模型。

### 2. 实例声明扫描器

新增 `InstanceDeclarationLoader` 类，在世界目录下**递归扫描所有** `instances/` 子目录：

```python
class InstanceDeclarationLoader:
    @staticmethod
    def scan(world_dir: str) -> list[dict]:
        """扫描世界 agents/ 目录下所有 instances/ 子目录"""
        world_path = Path(world_dir)
        agents_dir = world_path / "agents"
        declarations = []
        if not agents_dir.exists():
            return declarations
        for instances_dir in agents_dir.rglob("instances"):
            if not instances_dir.is_dir():
                continue
            for yaml_file in instances_dir.glob("*.instance.yaml"):
                with open(yaml_file, "r", encoding="utf-8") as f:
                    decl = yaml.safe_load(f)
                decl["_source_file"] = str(yaml_file)
                declarations.append(decl)
        return declarations
```

### 3. WorldRegistry 修改

```python
class WorldRegistry:
    def __init__(
        self,
        base_dir: str = "worlds",
        global_model_paths: list[str] | None = None,  # 新增：全局模型搜索路径
        metric_store_factory=None,
    ):
        ...
        self._global_model_paths = global_model_paths or []
```

`load_world()` 在初始化 `InstanceManager` 之后、调用 `StateManager.restore_world()` 之前，执行实例声明加载：

```python
# 在 load_world() 中，InstanceManager 创建后
from src.runtime.instance_declaration_loader import InstanceDeclarationLoader
from src.runtime.model_resolver import ModelResolver

resolver = ModelResolver(world_dir, self._global_model_paths)

decls = InstanceDeclarationLoader.scan(world_dir)
for decl in decls:
    model_dir = resolver.resolve(decl["modelId"])
    if model_dir is None:
        logger.warning("Model %s not found for instance %s", decl["modelId"], decl["id"])
        continue
    
    model = ModelLoader.load(model_dir)
    
    # 合并模型默认值
    merged_attrs = merge_defaults(model.get("attributes", {}), decl.get("attributes", {}))
    merged_vars = merge_defaults(model.get("variables", {}), decl.get("variables", {}))
    
    im.create(
        world_id,
        decl["modelId"],
        decl["id"],
        model=model,
        state={"current": decl.get("state"), "enteredAt": None} if decl.get("state") else {"current": None, "enteredAt": None},
        attributes=merged_attrs,
        variables=merged_vars,
        memory=decl.get("memory", {}),
    )
```

## 边界情况

1. **实例 ID 冲突**：声明加载在世界启动的早期阶段执行（在 `StateManager.restore_world()` 之前）。如果声明中的 `id` 与数据库中已存在的实例冲突，声明覆盖数据库——因为 `.instance.yaml` 代表当前期望状态，而数据库是上一次运行时的旧状态。覆盖前记录 warning 日志。
2. **模型不存在**：跳过该实例，记录 error 日志，不阻断世界启动。
3. **世界中无 instances/ 目录**：不影响，世界正常启动为空（向后兼容）。
4. **binding 引用不存在的外部源**：加载时仅记录绑定关系，不验证外部源是否存在（运行时由 bindings 解析器处理）。
5. **世界模型与全局模型同名**：世界私有模型优先，全局模型被忽略。这是有意设计——允许世界对全局模型进行覆盖和定制。

## 后续扩展

- **动态实例模板**：在任意 `instances/` 旁增加 `templates/` 子目录，放 `.template.yaml`，定义动态实例的默认配置。
- **实例分组/标签**：实例文件增加 `tags` 字段，支持按标签批量操作。
- **环境覆盖**：世界目录下支持 `prod/`、`dev/` 等环境子目录，按启动环境加载不同配置。

## 一句话总结

在世界目录下按照 `{namespace}/{modelId}/{model|instances}` 结构与全局模型对齐，扫描 `*/instances/*.instance.yaml` 文件，解析 modelId → 世界优先搜索模型 → 合并默认值 → 自动创建实例，让常驻实例随世界启动而加载。
