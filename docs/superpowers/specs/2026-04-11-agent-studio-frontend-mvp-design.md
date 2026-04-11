# Agent Studio Frontend MVP Design

## Goal

将当前以 schema、样例 JSON 和设计文档为主的仓库，演进为一个基于 `React + Ant Design 5 + Vite` 的前端项目，用于完成以下核心任务：

- 管理 agent model
- 管理 model 下的 agent instance
- 以结构化表单编辑高频字段
- 以 JSON 编辑器处理复杂配置块

本次目标是构建一个面向配置与管理的一体化 MVP，而不是实时运维平台、监控大屏或通用低代码引擎。

## Context

当前仓库已经具备较清晰的领域抽象：

- `model.json` 表达 agent model 定义
- `ladle_001.json` 表达 agent instance 运行态
- `schema/agent-instance-v2.schema.json` 约束实例结构
- `AGENT.md` 定义了 `embodiment / reflex / cortex` 方法论和顶层字段边界
- `db-design.md` 与 `openapi/*.json` 给出了后续数据层和接口层方向

这意味着前端不需要重新发明领域模型，而应围绕已有抽象进行类型化、分层化和界面化。

## Scope

### In Scope

- 模型列表与模型详情页
- 模型基础信息编辑
- 模型 `attributes / variables` 的结构化编辑
- 模型复杂块的 JSON 编辑
- 某模型下的实例列表
- 实例详情页
- 实例 `metadata / attributes / variables / bindings` 的结构化编辑
- 实例 `memory / activeGoals / currentPlan / extensions` 的 JSON 编辑
- Mock API 与 `localStorage` 持久化
- 基于 seed 数据初始化模型与实例

### Out of Scope

- 真实后端接入
- WebSocket 或实时流式运行态同步
- 可观测性大屏
- 完整服务调用控制台
- 状态机图形化编辑器
- `rules / services / states / transitions / goals / decisionPolicies` 的结构化编辑器
- 多用户协作、权限系统、审计系统

## Product Position

本次前端的定位是“配置与管理工作台”，不是“实时控制台”。

因此有以下取舍：

- 模型是一级主线
- 实例作为模型下的资源进行管理
- 结构化编辑优先覆盖高频、强结构字段
- 复杂、低频、嵌套深的块保持 JSON 编辑
- 强调显式保存、稳定反馈、清晰边界

## Information Architecture

推荐采用“模型为主线”的导航方式。

### Routes

- `/`
  重定向到 `/models`
- `/models`
  模型列表页
- `/models/:modelId`
  模型详情工作台
- `/models/:modelId/instances/:instanceId`
  实例详情页
- `/settings`
  设置页，本期仅提供应用信息展示与本地数据重置入口，不承载业务配置

### Navigation

左侧主导航仅保留：

- `Models`
- `Settings`

实例不作为一级导航项存在，只在模型详情页中显示和进入。

## Page Design

### 1. Models Page

用于展示模型集合与创建入口。

核心功能：

- 模型列表
- 搜索模型
- 创建模型
- 进入模型详情

展示信息建议包括：

- `metadata.name`
- `metadata.title`
- `metadata.description`
- 模型分组或标签
- 实例数量

### 2. Model Detail Page

这是模型管理的主工作台。

布局采用上下结构：

- 顶部：模型摘要与操作栏
- 中部：模型编辑 Tabs
- 底部：该模型下的实例列表

模型编辑 Tabs 推荐为：

- `Basic`
- `Attributes`
- `Variables`
- `Advanced JSON`

编辑边界如下：

- `Basic`
  编辑 `metadata`
- `Attributes`
  结构化编辑 `attributes`
- `Variables`
  结构化编辑 `variables`
- `Advanced JSON`
  编辑以下复杂块：
  `derivedProperties / rules / functions / services / states / transitions / behaviors / events / alarms / schedules / goals / decisionPolicies / memory / plans`

### 3. Instance Detail Page

该页面聚焦实例配置与查看，不承担复杂运行控制。

布局采用左右结构：

- 左侧：实例摘要、所属模型、基础状态、操作栏
- 右侧：实例编辑 Tabs

实例编辑 Tabs 推荐为：

- `Basic`
- `Attributes`
- `Variables`
- `Bindings`
- `Runtime JSON`

编辑边界如下：

- `Basic`
  编辑实例 `metadata`
- `Attributes`
  编辑实例属性值
- `Variables`
  编辑实例变量值
- `Bindings`
  结构化编辑绑定关系
- `Runtime JSON`
  编辑或查看：
  `memory / activeGoals / currentPlan / extensions`

`state` 在 MVP 中只做只读展示，不做状态机控制器。

## Type System

前端类型系统采用“两层类型 + 一层适配”的方式。

### 1. Domain Types

这一层直接对应领域抽象，作为页面、Mock API、持久化和校验的唯一数据基准。

建议至少包含：

- `AgentModel`
- `AgentModelMetadata`
- `AgentAttributeDefinition`
- `AgentVariableDefinition`
- `AgentJsonBlocks`
- `AgentInstance`
- `AgentInstanceMetadata`
- `AgentBinding`
- `AgentRuntimeSnapshot`
- `AgentGoalAssignment`
- `AgentPlan`

原则：

- 贴近 `model.json` 与 instance JSON
- 不掺杂 UI 展示状态
- 保存与持久化均以该层为准

### 2. UI Types

这一层服务于编辑器渲染。

建议至少包含：

- `FormFieldConfig`
- `FormSectionConfig`
- `DefinitionTableRow`
- `JsonBlockConfig`
- `ModelEditorTabKey`
- `InstanceEditorTabKey`
- `DirtyState`

原则：

- 只表达界面展示和交互所需信息
- 不反向污染领域对象

### 3. Adapter Layer

在领域类型与 UI 类型之间增加轻量适配层。

职责包括：

- 将 `attributes / variables` 映射为结构化表格与表单配置
- 将实例 `bindings` 映射为可编辑表格行
- 将复杂块映射为 JSON 编辑区配置
- 将模型和实例映射为摘要卡片数据

通过适配层，页面组件不直接消费底层 schema 细节。

## Editing Strategy

### Structured Editing

以下内容使用结构化编辑器：

模型：

- `metadata`
- `attributes`
- `variables`

实例：

- `metadata`
- `attributes`
- `variables`
- `bindings`

### JSON Editing

以下内容使用 JSON 编辑器：

模型：

- `derivedProperties`
- `rules`
- `functions`
- `services`
- `states`
- `transitions`
- `behaviors`
- `events`
- `alarms`
- `schedules`
- `goals`
- `decisionPolicies`
- `memory`
- `plans`

实例：

- `memory`
- `activeGoals`
- `currentPlan`
- `extensions`

### Save Behavior

- 编辑过程中允许按 Tab 分块修改
- 持久化时以“完整模型对象”或“完整实例对象”为单位保存
- 不做自动保存
- 用户显式点击 `Save` 才提交
- `Reset` 回退到最近一次保存版本
- 存在未保存修改时，页面显示 `dirty state`
- 路由离开前触发未保存确认

## Data Layer

数据层采用 `Mock API + localStorage`。

### Seed Strategy

首次启动时，用仓库中的示例数据生成初始数据集：

- `model.json`
- `ladle_001.json`

建议在前端内部维护标准化 seed 结构，例如：

- `seedModels`
- `seedInstances`

### Layering

建议分为三层：

1. `mock repository`
   负责读写 `localStorage`
2. `mock service`
   暴露异步 CRUD 接口，模拟网络延迟和错误
3. `page hooks / module hooks`
   负责请求、提交、错误状态和刷新

数据流为：

`seed data -> repository -> mock service -> page/module hooks -> components`

### Future Compatibility

后续接入真实后端时，应尽量只替换 `mock service` 和 `repository` 层，而不改动页面组件和编辑器组件。

## Component Boundaries

目录命名采用 `pages + modules + shared`，避免页面膨胀，也避免术语过度抽象。

### Recommended Structure

```text
src/
  pages/
    models/
      index.tsx
      detail.tsx
    instances/
      detail.tsx
    settings/
      index.tsx
  modules/
    models/
      components/
      hooks/
      adapters/
      services/
    instances/
      components/
      hooks/
      adapters/
      services/
  shared/
    components/
    hooks/
    lib/
    layout/
  mocks/
    data/
    repository/
    services/
  types/
    domain/
    ui/
```

### Model Module

建议至少包含：

- `ModelList`
- `ModelSummaryCard`
- `ModelEditorTabs`
- `ModelMetadataForm`
- `DefinitionTableEditor`
- `JsonBlockEditor`
- `CreateModelModal`
- `useModelList`
- `useModelDetail`
- `modelAdapters`

### Instance Module

建议至少包含：

- `InstanceListByModel`
- `InstanceSummaryCard`
- `InstanceEditorTabs`
- `InstanceMetadataForm`
- `InstanceAttributesForm`
- `InstanceVariablesEditor`
- `BindingTableEditor`
- `RuntimeJsonPanel`
- `CreateInstanceModal`
- `useInstanceDetail`
- `instanceAdapters`

## Validation Strategy

校验采用“两级校验 + 保存前统一校验”。

### 1. Structured Validation

针对结构化编辑区，进行即时校验：

- 必填校验
- 类型匹配
- `minimum / maximum`
- `nullable`
- `enum`

### 2. JSON Validation

针对 JSON 编辑区，进行两步校验：

- JSON 语法校验
- 块级结构校验

### 3. Object-Level Validation

点击保存时，对完整模型对象或完整实例对象进行一次统一校验，避免各个编辑块单独合法但组合后整体不合法。

## Error Handling

MVP 需要稳定、明确、保留用户输入的错误处理体验。

### Required Behaviors

- 列表加载失败时，展示错误态与重试按钮
- 保存失败时，保留当前表单和 JSON 编辑内容
- JSON 解析失败时，禁止保存
- 路由参数无效或资源不存在时，展示 404 风格空页
- `localStorage` 不可用或容量不足时，提示本地存储失败

### Feedback Pattern

- 字段错误使用内联提示
- JSON 块错误在编辑区顶部展示摘要
- 保存结果使用 `message` 或 `notification`
- 成功保存后更新最后保存时间

## Instance Creation Rules

新建实例时，推荐遵循以下默认规则：

- `modelId` 继承当前模型
- `metadata.name / title` 由用户填写
- `attributes` 按模型默认值初始化
- `variables` 按模型默认值初始化
- `bindings` 初始为空对象
- `memory / activeGoals / currentPlan / extensions` 初始为空结构
- `state` 在创建表单中为必填项
- 若模型定义了 `states`，创建表单默认选中 `states` 的第一个 key
- 若模型未定义 `states`，默认写入 `initialized`

## Testing Strategy

MVP 测试聚焦关键路径可信，不追求全面覆盖。

### Unit Tests

- domain type adapters
- validators
- repository
- mock service

### Component / Page Tests

- 模型列表加载与进入详情
- 模型 `metadata / attributes / variables` 编辑并保存
- 实例 `variables / bindings` 编辑并保存
- JSON 编辑区修改并保存
- 未保存离开确认

### Route Smoke Tests

- `/models`
- `/models/:modelId`
- `/models/:modelId/instances/:instanceId`

### Recommended Tools

- `Vitest`
- `React Testing Library`

E2E 不作为本期 MVP 的硬要求。

## Design Principles

### 1. Follow the Existing Domain

前端优先贴合现有 agent 抽象，不额外发明新的顶层业务概念。

### 2. Prefer Clear Boundaries

高频配置结构化，复杂配置 JSON 化，不追求所有块都通用渲染。

### 3. Keep the MVP Small

先做模型与实例的最小闭环，不提前建设监控大屏、控制中心和完整运行时系统。

### 4. Preserve Replaceability

Mock API、适配层和 UI 类型都应为后续接入真实后端预留替换空间。

## Open Questions Resolved in This Design

为避免后续实现产生分歧，本设计明确采用以下结论：

- 使用 `React + Ant Design 5 + Vite`
- 前端是一体化 MVP
- 主导航采用“模型为主线”
- 实例从属于模型
- 高复杂度块保留 JSON 编辑
- 类型分为 domain types 与 UI types
- 目录命名采用 `pages + modules + shared`
- 持久化采用 `Mock API + localStorage`
- MVP 以配置和查看为主，不做复杂控制台

## Implementation Target

本设计对应的首个可交付目标应满足：

- 可以查看模型列表
- 可以创建、查看、编辑模型
- 可以查看某模型下的实例列表
- 可以创建、查看、编辑实例
- 编辑结果在浏览器刷新后仍保留
- 高复杂度块可通过 JSON 编辑完成
- 保存、校验、未保存离开提示等基础体验完整可用
