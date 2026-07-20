# 阶段 13：turn kernel 策略学习总结

## 主题

本阶段的主题是：把散落在 agent loop 中的步骤判断抽成显式、可测试的 turn kernel，用状态和策略管理 phase、验证证据、空响应重试、步数预算与一次性 widening。

大白话讲，之前的 loop 像一个边走边临时决定方向的人：能到终点，但“现在为什么继续、为什么停止、为什么还要验证”都藏在 `if/while` 里。turn kernel 相当于给每一步配一个调度规则：loop 仍负责真正调用模型和工具，kernel 专门回答“当前处于什么阶段，下一步允许做什么”。

## 问题是什么

### 为什么要有这个阶段

阶段 3 的最小循环证明了 `model -> tool -> model -> final` 能跑通，但随着权限、session、checkpoint、memory 和日志加入，循环里的控制分支越来越多。如果状态分散在局部布尔值中，空响应、工具失败、预算耗尽和提前 final 会互相影响，测试也只能绕过整个 loop 间接验证。

更重要的是，“模型给了非空文本”不一定表示任务已经可靠完成。模型执行过工具后，需要有成功且非空的工具观察支撑 final；否则失败工具后直接说“完成”会把语言输出误当成事实。

### 本阶段具体要解决的问题

1. 显式表达 `explore -> execute -> verify` 三个 phase。
2. 用单一状态对象维护步数、空响应重试、工具结果、验证证据和停止原因。
3. 把 assistant/tool 步骤判断从 loop 挪到可直接单测的 policy 函数。
4. 工具行动后，阻止缺少成功证据的过早 final。
5. 最后一个基础步骤产生工具观察时，只增加一次预算，让模型有机会验证和收尾。
6. widening 已用尽后仍无 final，继续保留明确的 max steps 硬边界。

## 解决方案

### 最小解决方案

- 新增 `TurnRecurrentState`，保存单轮反复使用的控制状态。
- 新增 `TurnStepPolicy`，表示某一步开始时的 phase、剩余预算和验证责任快照。
- `derive_turn_step_policy` 只根据累计状态推导策略。
- `decide_assistant_turn` 把模型文本分为 progress、retry、guard、fallback 和 final。
- `decide_tool_turn` 把工具结果折叠为成功观察、错误数和有界 evidence 摘要。
- `agent_loop` 保留模型调用、工具执行、消息写入和回调，只消费 kernel 决策。
- 默认基础预算耗尽且必须继续时增加 1 步；`widening_active` 保证整轮只增加一次。
- 调用方可传 `widening_extra_steps=0` 禁用扩宽，获得严格硬上限。

### 为什么这个方案足够

阶段 13 的目标是理解 harness 控制点，不是复制完整控制论。当前三个 phase、单轮状态、验证守卫和一次性预算扩宽已经能展示“状态 -> policy -> 决策 -> 执行 -> 新状态”的核心闭环。真实项目的 task graph、profile、pause/await-user、max-token recovery、compaction、layered context 和复杂 widening 信号依赖更多尚未实现的系统，提前复制只会形成空壳。

## 工作原理

### 心智模型

把 turn kernel 看成一个小型调度器，而不是模型或工具执行器：

- `TurnRecurrentState` 是这一轮的记分板，记录已经发生的事实。
- `derive_turn_step_policy` 是赛前战术板，根据记分板说明本步骤重点。
- `decide_assistant_turn` 和 `decide_tool_turn` 是裁判，把本步骤结果归类。
- `agent_loop` 是执行现场，真正调用模型、运行工具并写消息历史。

kernel 不读取文件、不调用 provider、不触发权限审批，因此可以用纯内存对象快速覆盖所有边界。

### 核心对象解释

#### `TurnRecurrentState`

它是单轮唯一的控制状态源。`step/max_steps` 管预算；`empty_response_retry_count` 管有限重试；`saw_tool_result` 决定是否进入验证责任区；成功工具数和有界摘要共同构成 verification evidence；`widening_active` 与迁移次数防止反复扩预算；`stop_reason` 保存最终终止原因。

`record_tool_result` 只把成功且非空的输出记为证据。失败输出有诊断价值，但不能证明任务完成；`ok=True` 但空输出也不足以支持结论。

#### `TurnStepPolicy`

它是某一步的不可变含义快照，不承担跨步累计。当前字段回答：这是第几步、处于哪个 phase、还剩多少预算、是否要求验证、证据是否就绪、是否允许 widening、是否已经 widened。

#### `derive_turn_step_policy`

第一步为 `explore`；没有工具观察的后续步骤为 `execute`；只要出现工具结果，后续步骤进入 `verify`。有效预算耗尽且尚未 widening 时，策略开放一次扩宽机会。函数同时把 phase 写回 recurrent state，便于诊断和测试。

#### `decide_assistant_turn`

progress 继续循环；首次空响应返回 retry 并消费一次额度；再次空响应返回 fallback；verify 阶段缺少成功非空证据时返回 guard；其他非空文本才是 final。这样“文本非空”和“允许结束”不再是同一个判断。

#### `decide_tool_turn`

工具已经由 registry 执行完毕，这个函数不重复执行工具，只记录结果状态并返回 continue。这个边界确保 kernel 不接触权限、文件系统或工具异常隔离细节。

#### `_widen_if_needed`

loop 只有在当前结果必须继续时才调用它，例如 progress、空响应 retry、verification guard 或工具结果。若预算刚好耗尽，state 增加一个步骤；若已经 widened 或配置为 0，则不改变预算。final 和 fallback 不会为了“用完额度”而无意义扩宽。

### 当前核心流程

```text
用户消息
  -> TurnRecurrentState
  -> begin_step 占用预算
  -> derive_turn_step_policy
       第一步 explore
       未见工具的后续步 execute
       已见工具结果 verify
  -> model.next
       assistant -> decide_assistant_turn
       tool_calls -> registry.execute -> decide_tool_turn
  -> 更新消息与 recurrent state
  -> final / fallback / max_steps，或继续下一步
```

验证守卫流程：

```text
tool failure 或成功但空输出
  -> saw_tool_result=True
  -> phase=verify
  -> model 提交 final
  -> evidence_ready=False
  -> guard：final 不写入 assistant 终态
  -> 请求一次具体验证或明确 blocker
```

widening 流程：

```text
最后一个基础步骤产生“必须继续”的结果
  -> remaining_steps=0
  -> activate_widening(extra_steps=1)
  -> 获得一次验证/收尾机会
  -> 再次到达边界时拒绝扩宽
  -> 仍无 final 则 max_steps 停止
```

## 对应核心文档

参考项目路径：`D:\JavaProject\MiniCode-Python-main`

- `minicode/turn_kernel.py`
  - 对照 `TurnRecurrentState`、`TurnStepPolicy`、assistant/tool decision 和 phase 推导。
  - 学习“状态与策略集中、执行留在 loop”的边界。
  - 理解真实实现如何加入 budget signals、strict verification、widening reason 和 typed stop reason。
- `tests/test_turn_kernel.py`
  - 对照 phase、验证失败、widening 幂等与工具决策的直接单元测试。
- `minicode/agent_loop.py`
  - 回看真实 loop 如何消费 kernel 决策，而不是让 kernel 直接接管 provider 和工具。

## 学习产出

### 新增代码

- `minicode_lite/turn_kernel.py`
  - recurrent state、step policy、assistant/tool decision、phase 推导、证据守卫和一次性 widening。
- `minicode_lite/agent_loop.py`
  - 改为消费 turn kernel，新增 `widening_extra_steps` 配置，保留原有消息、回调、权限和日志边界。

### 新增测试

- `tests/test_turn_kernel.py`
  - 直接验证 phase、预算、空响应、verification guard、证据通过、widening 幂等和非法预算。
- `tests/test_agent_loop.py`
  - 验证最后基础步骤工具调用后的自动 widening，以及失败工具后的过早 final 被守卫拦截。
- `tests/test_observability.py`
  - 严格 max steps 日志用例显式禁用 widening，保留停止原因覆盖。

### 新增文档

- `docs/stage-summaries/stage-13-turn-kernel-policies.md`
  - 保存本阶段心智模型、流程、差异、误区、自测与面试题库。
- `MINICODE_HARNESS_LEARNING_PLAN.md`
  - 记录阶段 13 完成状态和验证结果。

### 本阶段最终能力

- agent turn 的控制状态不再散落在 loop 局部变量中。
- 每个模型步骤都有明确 phase 和预算快照。
- 空响应最多重试一次。
- 工具之后的 final 必须有成功且非空的观察支持。
- 基础预算边界可自动扩宽一次，也可显式禁用。
- widening 用尽后仍由 max steps 硬停止。

## 测试验证

执行的验证命令：

```powershell
python -m pytest -q
python -m compileall -q minicode_lite
git diff --check
```

2026-07-20 的全量结果：

```text
156 passed, 1 skipped
```

跳过项仍是需要显式启用并使用真实配置的 live Qwen 测试。

重点验证行为：

- phase 按 `explore -> execute -> verify` 迁移。
- remaining steps 在边界归零，严格模式可用 `widening_extra_steps=0` 命中 max steps。
- 空响应首次 retry、第二次 fallback。
- 失败工具结果不会成为 verification evidence。
- 守卫消息使用 progress 角色，不会把被拒绝的文本保存为最终 assistant。
- 成功非空工具观察允许 verified final。
- widening 第一次扩 1 步，第二次调用返回 False 且不再改预算。
- 权限生命周期、工具消息配对、回调与结构化 stop 日志均保持回归通过。

## 和真实 MiniCode-Python 的差异

### 保留的设计

- recurrent state 是单轮控制事实源。
- 每步 policy 从累计状态推导，而不是散落在 UI 或工具中。
- assistant 与 tool 都返回结构化 decision。
- verify 阶段能阻止没有证据支持的 final。
- widening 是显式且幂等的状态迁移。

### 简化的设计

- phase 规则只有三条，没有 profile 和按比例计算 verify threshold。
- 任意成功非空工具结果都算最小证据，不分析它是否真正对应用户验收标准。
- widening 只在预算边界增加固定一步，不计算错误率、停滞原因或替代路径。
- stop reason 仍沿用现有四类，没有 `await_user`、`verification_failed`、`widen_needed` 等完整类型。
- 没有 stable task pack、task graph、protected context、compaction 和 runtime event category。

### 后续再实现的设计

- 阶段 14 的 skills 只作为新工具来源接入 registry，不应破坏 kernel 边界。
- 阶段 15 的 REPL/TUI 可展示 phase、guard 和 widening，但不能重新实现决策。
- 阶段 16 可加入端到端验收证据，并评估 evidence 的任务相关性。
- 真正需要复杂长任务时，再引入 profile、stall signal、strict verification 和 typed pause/handoff。

## 常见误区

- 误区：turn kernel 是把整个 agent loop 搬到新文件。
  - kernel 只负责状态和决策；模型调用、工具执行、权限、消息与回调仍属于 loop。
- 误区：进入 verify 就必须立刻结束。
  - verify 表示当前责任是检查证据；证据不足时应继续行动或报告 blocker，而不是强行 final。
- 误区：任何 tool result 都是成功证据。
  - 失败输出只能证明工具失败；成功但空输出也未提供可引用事实。
- 误区：widening 等于取消 max steps。
  - 当前只增加一次固定预算，之后仍有明确硬上限。
- 误区：第一步必须调用探索工具才算 explore。
  - phase 表示策略重点，不强制某种具体输出；简单任务第一步可以直接 final。
- 误区：guard 应把模型原 final 写入 assistant 历史。
  - 被拒绝的 final 不能伪装成终态；当前只记录 guard progress 和验证 nudge。

## 复习提示

下次复习时，重点理解：

- recurrent state 与 step policy 为什么一个可变、一个是快照。
- phase 为什么由已发生的外部观察驱动。
- 为什么证据要同时满足成功和非空。
- 为什么 widening 只在“必须继续”时触发。
- loop 与 kernel 的职责边界如何降低测试成本。

可以尝试自己回答：

1. 第一步直接返回完整答案时，为什么不需要强制进入 execute 和 verify？
2. 工具返回 `ok=True, output=""` 后模型声称完成，会发生什么？
3. `max_steps=1` 且第一步调用工具时，默认与禁用 widening 的结果分别是什么？
4. 为什么 `derive_turn_step_policy` 不直接调用 `activate_widening`？
5. 新增 `load_skill` 工具时，需要修改 kernel 吗？

## 面试高频问题与参考答案

### 1. turn kernel 在 agent harness 中解决什么问题？

**参考答案：** turn kernel 把单轮中的状态推进和分支规则从执行循环中抽离，使 phase、重试、验证和预算成为显式、可直接测试的策略。loop 继续负责副作用，kernel 负责回答下一步如何处理。这样新增控制规则时不必在模型、工具和 UI 分支中重复修改，也更容易证明 max steps 和 guard 等边界不会失效。

### 2. `TurnRecurrentState` 和 `TurnStepPolicy` 有什么区别？

**参考答案：** recurrent state 是跨步骤累积的可变事实，例如已经调用几次模型、是否见过工具结果、是否有证据、是否 widened；step policy 是根据这些事实为当前步骤生成的快照，例如当前 phase、剩余预算和验证要求。前者回答“发生过什么”，后者回答“这一刻该遵循什么规则”。把两者混在一起会让历史事实和临时判断互相覆盖。

### 3. phase 如何从 explore 迁移到 execute 和 verify？

**参考答案：** 第一模型步骤是 explore，用于理解或直接解决简单任务；如果后续仍没有工具观察，就进入 execute，表示需要采取具体行动；只要出现工具结果，后续步骤进入 verify，因为外部行动已经发生，模型必须根据观察判断是否成功并可靠收尾。当前规则有意简单，真实项目还会结合 profile、剩余预算和 strict verification。

### 4. 取舍题：为什么不一次复制真实 MiniCode 的完整 turn kernel？

**参考答案：** 轻量版目前没有 task graph、layered context、compaction、handoff 和多种运行 profile，复制相关结构不会产生真实控制价值，只会让学生追踪大量空状态。本阶段保留状态、policy、decision、证据守卫和幂等 widening 这条核心链，足以理解 harness 控制点；复杂信号应在对应依赖存在且有测试场景时再增加。

### 5. 为什么失败工具结果不能作为 verification evidence？

**参考答案：** 失败结果能解释“为什么没完成”，但不能支撑“任务已经完成”。如果把 `ok=False` 的错误文本当证据，模型可以在读写或测试失败后直接提交 final，守卫就失去意义。当前最小规则要求 `ok=True` 且输出非空；边界是它还不判断证据是否与具体验收标准相关，这属于后续更严格验证。

### 6. widening 为什么只触发一次？

**参考答案：** widening 的作用是避免最后基础步骤刚产生工具观察就被硬停，让模型多一次验证或收尾机会，而不是无限续命。`widening_active` 是幂等门闩，第一次迁移增加预算并记次数，之后调用返回 False。若额外一步仍不能完成，就由有效 max steps 停止，保证成本和时间仍有上界。

### 7. 测试策略为什么同时需要 kernel 单测和 loop 集成测试？

**参考答案：** kernel 单测能用纯状态快速覆盖 phase、空响应、guard 和 widening 边界，失败时定位清楚；loop 集成测试验证这些 decision 真正改变消息历史、模型调用次数和工具闭环。只测 kernel 可能接线错误，只测 loop 又难穷举状态组合。两层测试分别保护规则正确性和接入正确性。

### 8. 场景题：工具执行失败后模型立即回复“修改完成”，系统应怎样处理？

**参考答案：** `decide_tool_turn` 记录 `saw_tool_result=True` 和错误数，但不生成成功 evidence；下一步 policy 进入 verify。`decide_assistant_turn` 看到非空 final 但 evidence 未就绪，返回 guard，不把“修改完成”写成最终 assistant，而是记录验证提示并要求运行具体验证或说明 blocker。若预算耗尽可 widening 一次，之后仍无可靠结果则 max steps 停止。

### 9. 场景题：启用 widening 后 turn 仍然超过预期成本，如何排查？

**参考答案：** 先检查调用方的基础 `max_steps` 和 `widening_extra_steps`，再断言 state 的 `widening_transition_count` 是否始终小于等于 1。若模型调用次数超过两者之和，问题在 loop 是否绕过 `has_remaining_steps`；若预算被多次增加，问题在是否复用了同一个 recurrent state 或破坏了 `widening_active`。日志中的最终 steps 应与有效 max steps 对照。需要严格预算时传 0 禁用 widening。

### 10. `decide_tool_turn` 为什么不直接执行工具？

**参考答案：** 工具执行涉及注册表查找、输入校验、权限、工作区、副作用、异常隔离和生命周期回调，这些都属于 loop 与 tooling 层。kernel 若直接执行工具就不再是可预测的策略层，也难以纯单测。它只接收已经标准化的 `ok/output`，折叠成控制状态并决定继续，这保持了副作用边界。

### 11. 空响应 retry 与 widening 如何配合？

**参考答案：** 首次空响应由 kernel 消费一次 retry 额度并返回 nudge。如果这恰好是最后基础步骤，loop 因为决策要求继续而激活一次 widening，让重试真正有预算执行。第二次空响应由 kernel fallback 结束，不会因为还有 widening 机制而无限重试。重试次数和总步骤预算是两道独立边界。

### 12. 当前实现与真实 MiniCode-Python 的核心差异是什么？

**参考答案：** 轻量版保留 recurrent state、per-step policy、结构化 decision、phase、verification guard 和幂等 widening；简化了 phase 阈值、证据判断、stop reason 和 widening 信号。真实实现还结合任务 profile、工具错误与停滞证据、strict verification、stable task pack、task graph、compaction 和 typed pause/handoff。轻量版先把最小控制回路做实，再让后续能力按需要接入。

## 下一阶段衔接

本阶段解决了：

```text
agent loop 的关键策略不再埋在局部 if/while 中，而是由显式状态、phase、证据与预算规则驱动。
```

阶段 14 要解决：

```text
当前工具集合仍是固定代码注册，尚不能发现并加载项目本地 skills。
```

本阶段产物会这样支撑下一阶段：

- skills 作为新的工具来源进入 `ToolRegistry`，无需侵入 turn kernel。
- skill 工具结果仍通过统一 `ToolResult` 进入 verification evidence 流程。
- phase 和预算边界能约束模型加载、执行、验证 skill 的步骤，不让扩展点绕过核心 loop。
