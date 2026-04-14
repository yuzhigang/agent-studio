# 钢包调度员智能体设计文档（对齐 Agent Studio v2 PRD）

## 1. 文档目的

本文档将“钢包调度员”场景，按 [prd.md](./prd.md) 的 v2 设计思路落到可实施的模型与运行流程中，回答三个问题：

1. 这个场景在当前 schema 中如何表达。
2. 配包决策流程在 `reflex / cortex` 中如何分工。
3. 从事件输入到任务下发、异常重调度，如何形成闭环。

---

## 2. 场景边界与角色

### 2.1 目标场景

当“转炉需要配包”指令到达时，钢包调度员需要在多个钢包中选择最优候选，并下发任务。

### 2.2 参与智能体

- `LadleDispatcher`（钢包调度员，调度型 agent）
- `Ladle`（钢包实体 agent）
- `Converter`（转炉实体 agent）
- `Crane`/`Transport`（执行搬运的实体 agent，可选）

### 2.3 设计原则（对齐 PRD）

- 硬约束在 `rules`，优化目标在 `goals/plans`。
- `functions` 只做计算，不写状态。
- `states/transitions` 只描述状态与拓扑，不放副作用。
- 所有副作用统一进 `behaviors`。
- cortex 决策不能绕过规则与权限边界。

---

## 3. 输入驱动与路由

按 PRD 的“三通道”设计，钢包调度员主要接收：

1. `EVENT`：转炉请求配包（如 `converterNeedLadle`）。
2. `COMMAND`：人工强制配包、撤销配包、锁包等。
3. `SCHEDULE`：周期性健康检查、任务超时扫描。

典型路由：

- 普通配包请求先走 `behaviors(event)`，触发候选筛选与打分。
- 高风险或冲突情形按 `decisionPolicies.escalateWhen` 升级到 cortex。
- cortex 输出受 `plans.allowedServices` 限制的执行步骤。

---

## 4. 钢包调度员的字段映射（按 PRD 顶层 schema）

## 4.1 metadata

- 名称、版本、适用产线、作者、审计策略。

## 4.2 attributes（静态边界）

- `maxDispatchWindowSec`：最长允许调度窗口。
- `defaultReserveCandidates`：默认保留备选包数量。
- `temperatureSafetyMargin`：温度安全裕量。

## 4.3 variables（运行态）

- `pendingRequests`：待处理配包请求队列。
- `activeAssignments`：已下发未完成的配包任务。
- `resourceLocks`：钢包锁、路径锁。
- `dispatchMode`：`normal / degraded / emergency`。

## 4.4 derivedProperties（只读计算视图）

- `queueLength`：待调度长度。
- `onTimeRateRolling`：滚动准时率。
- `conflictRateRolling`：滚动冲突率。

## 4.5 rules（硬约束）

只放确定性规则，例如：

- `ladleAvailable`：钢包状态必须可用（非检修、非故障、未占用）。
- `gradeCompatible`：钢种匹配必须满足工艺矩阵。
- `temperatureSufficient`：预计到达温度必须高于阈值。
- `refractoryLifeSafe`：耐材寿命满足最低剩余次数。
- `etaBeforeDeadline`：预计到达时间不晚于业务截止时间。
- `permissionCheck`：强制改派需特定角色。

违规动作示例：

- 安全类不满足：`reject`
- 轻微风险：`warn`
- 强制人工指令：`override`（必须审计）

## 4.6 functions（纯计算）

- `getCandidateLadles(request)`：候选钢包集合。
- `estimateArrivalTime(ladleId, destination)`：到达时间估算。
- `estimateTempAtArrival(ladleId, eta)`：到达温度估算。
- `scoreCandidate(ladle, request, context)`：候选评分。
- `rankCandidates(candidates)`：排序输出。

说明：上述函数只读上下文，禁止直接改 `variables/memory/state`。

## 4.7 services（动作入口）

- `createDispatchTask`
- `lockLadle`
- `assignLadleToConverter`
- `releaseLadle`
- `cancelDispatchTask`
- `manualOverrideAssignment`

每个 service 使用 `rules.pre/post` 与 `permissions.roles` 进行约束。

## 4.8 states/transitions（状态机拓扑）

建议状态：

- `idle`
- `evaluating`
- `assigning`
- `monitoring`
- `replanning`
- `degraded`

建议迁移：

- `idle -> evaluating`（收到配包请求）
- `evaluating -> assigning`（选出候选）
- `assigning -> monitoring`（任务下发成功）
- `monitoring -> replanning`（延迟/冲突/故障）
- `replanning -> assigning`（重算后再次下发）
- 任意状态 `-> degraded`（系统级异常）

## 4.9 behaviors（副作用归宿）

- 事件触发后写入 `pendingRequests`。
- 调用计算函数后更新候选排序缓存。
- 执行 service（锁包、下发、回滚）。
- 触发出站事件（`ladleAssigned`, `dispatchFailed`, `dispatchReplanned`）。
- 写审计与告警。

## 4.10 events（出站事件契约）

- `ladleAssignmentProposed`
- `ladleAssigned`
- `ladleAssignmentRejected`
- `dispatchTimeoutDetected`
- `dispatchReplanned`

## 4.11 alarms

- `noCandidateAvailable.critical`
- `dispatchDelay.warning`
- `frequentReplan.warning`
- `lockContention.warning`

## 4.12 schedules

- 每 30s 扫描超时任务。
- 每 5min 计算滚动绩效指标。
- 每 1min 扫描死锁或锁泄露。

## 4.13 goals（优化目标）

- `safetyFirst`（优先级最高）
- `onTimeDelivery`
- `temperatureQuality`
- `resourceBalance`（减少单包过度使用）
- `replanMinimization`

## 4.14 decisionPolicies

- 默认 `preferredMode = reflex`。
- 出现目标冲突、连续失败、路径冲突、无可用候选时升级到 cortex。
- `timeoutFallback = freeze_and_alert` 或 `fallback_best_effort`（由业务定）。

## 4.15 memory（cortex 结构化记忆）

- `lastNAssignments`
- `gradeToLadleHistory`
- `abnormalPatterns`
- `lastDecisionRationale`
- `temporaryBlackListLadles`

## 4.16 plans（结构化计划模板）

计划示例：`ladleAssignmentPlan`

- `stepSchema`: `{ service, args }`
- `allowedServices`:
  - `lockLadle`
  - `assignLadleToConverter`
  - `releaseLadle`
  - `cancelDispatchTask`
- `successCondition`: 目标转炉在时限内获得可用钢包

---

## 5. 配包决策流程（端到端）

## 5.1 Step 1：接收请求

输入事件 `converterNeedLadle`，包含：

- `requestId`
- `converterId`
- `heatId`
- `steelGrade`
- `requiredWeight`
- `requiredByTime`
- `priority`

behavior 将请求写入 `pendingRequests`，触发状态迁移 `idle -> evaluating`。

## 5.2 Step 2：候选集构建（硬过滤）

执行 `getCandidateLadles`，先按规则过滤：

- 状态可用
- 非锁定
- 钢种兼容
- 寿命可用
- 温度可达
- 时效可达

如果候选为空，触发 `noCandidateAvailable.critical`，并升级 cortex。

## 5.3 Step 3：候选评分与排序（优化层）

对每个候选计算：

- `etaScore`：到达时间越短越高
- `tempScore`：到达温度风险越低越高
- `gradeScore`：钢种历史匹配与稳定性
- `balanceScore`：资源均衡
- `conflictScore`：路径/锁冲突风险

示例总分：

`totalScore = w1*etaScore + w2*tempScore + w3*gradeScore + w4*balanceScore - w5*conflictPenalty`

## 5.4 Step 4：二次校验与锁定

在下发前执行 `rules.pre` 二次检查，确认候选未被并发占用；通过后调用 `lockLadle`。

## 5.5 Step 5：下发配包任务

调用 `assignLadleToConverter`，并发布 `ladleAssigned` 事件，进入 `monitoring` 状态。

## 5.6 Step 6：执行监控与异常重调度

监控执行回执，若出现：

- 超时未到位
- 钢包故障
- 温度跌破阈值
- 路径冲突

则触发 `monitoring -> replanning`，释放原锁，重新评估备选并改派。

---

## 6. reflex 与 cortex 分工建议

## 6.1 reflex 负责

- 常规请求快速配包（毫秒级到秒级）。
- 规则硬过滤与确定性拒绝。
- 任务下发和状态维护。

## 6.2 cortex 负责

- 目标冲突（时效 vs 温度 vs 均衡）权衡。
- 连续失败后的策略调整。
- 异常聚合分析与重规划。
- 在 `allowedServices` 白名单内生成执行计划。

---

## 7. 审计与可观测性要求

至少记录：

- 请求接收时间、决策耗时、下发时间、完成时间。
- 候选集合与淘汰原因（规则命中明细）。
- 最终选择得分与权重快照。
- override 操作人、理由、影响范围。
- 每次重调度原因与结果。

关键指标：

- 配包成功率
- 准时到位率
- 平均重调度次数
- 无候选告警频率
- 锁冲突率

---

## 8. 与当前示例模型的关系

当前仓库中的 `model.json` 更偏“钢包实体 agent”；本文档定义的是“钢包调度员 agent”。

建议落地方式：

1. 保留现有 `Ladle` 模型作为被调度对象。
2. 新增 `LadleDispatcher` 模型，按本文字段设计实现。
3. 通过事件总线与 `links` 建立调度员和钢包/转炉/运输设备的协同关系。

---

## 9. 最小可用模型骨架（示意）

```json
{
  "$schema": "https://agent-studio.io/schema/v2",
  "metadata": { "name": "ladle_dispatcher", "title": "钢包调度员" },
  "attributes": {},
  "variables": {},
  "derivedProperties": {},
  "rules": {},
  "functions": {},
  "services": {},
  "states": {},
  "transitions": {},
  "behaviors": {},
  "events": {},
  "alarms": {},
  "schedules": {},
  "goals": {},
  "decisionPolicies": {},
  "memory": {},
  "plans": {}
}
```

---

## 10. 分阶段实施建议

1. 第 1 阶段：规则过滤 + 基础评分 + 单次下发（无重调度）。
2. 第 2 阶段：锁机制 + 超时监控 + 自动改派。
3. 第 3 阶段：cortex 接管冲突场景 + 记忆驱动策略优化。
4. 第 4 阶段：多目标权重在线调优与仿真回放评估。

