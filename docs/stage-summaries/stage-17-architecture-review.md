# 阶段 17：回顾真实 MiniCode-Python 架构学习总结

## 主题

本阶段在 MiniCode Lite 已经完成一轮实现之后，重新阅读真实 MiniCode-Python 的结构文档，并把两套代码放进同一张架构地图里比较。重点不是复制更多代码，而是回答：哪些模块属于最小 harness 核心，哪些是产品面，哪些是高级优化层。

大白话讲：前 16 个阶段像是把一辆教学用小车装起来；阶段 17 是打开真实车辆的维修手册，确认方向盘、发动机和刹车分别对应什么，再决定哪些复杂配件暂时不装。能说清边界，比盲目增加文件更重要。

## 问题是什么

### 为什么要有这个阶段

如果只看自己的 Lite 实现，容易把当前文件列表误认为完整架构；如果直接照抄真实项目，又会把 provider、TUI、MCP、压缩和控制论的复杂状态过早引入。架构回顾把“相同的核心契约”和“有意的简化”明确写出来，为后续扩展建立判断标准。

### 本阶段具体要解决的问题

1. 找出 Lite 与真实项目共同的核心数据流和模块边界。
2. 解释真实项目增加的产品面、高级优化层以及它们为何可以后置。
3. 把真实项目的测试思想迁移成 Lite 可运行的验证方式。

## 解决方案

### 最小解决方案

- 对照真实项目的 `Docs/Documentation/STRUCTURE.md` 和核心模块职责。
- 新增根目录 `ARCHITECTURE_NOTES.md`，用分层表、模块对照、数据流和后置清单记录结论。
- 新增文档契约测试，确保核心模块映射和最小依赖方向仍在回顾文档中。
- 实际运行 Lite 的全量测试、headless 只读分析入口和 session replay，验证回顾建立在可运行证据上。

### 为什么这个方案足够

阶段 17 的产物是架构理解，不是新增运行时功能。已有集成测试和发布门禁已经覆盖核心行为，因此只补一个低成本文档测试即可保护学习产物；完整结构检查、依赖图生成和 artifact bundle 属于真实项目的后续发布能力。

## 工作原理

### 你要建立的心智模型

把 harness 看成一条有边界的流水线：入口收集任务，模型适配器只负责产生统一步骤，agent loop 编排步骤，工具注册表执行受约束能力，权限和 workspace 保护副作用，session 保存证据，产品面和 readiness 负责观察与操作。高级模块可以围绕流水线提供反馈，但不应让最小链路依赖它们。

### 核心对象解释

#### `agent_loop.py` 与 `turn_kernel.py`

前者负责副作用和消息序列，后者负责单轮策略。分开后，空回答重试、verification 和 widening 可以独立测试，loop 也不会把停止原因隐藏在一条复杂 `while` 中。

#### `ToolRegistry`、`PermissionManager` 与 `ToolContext`

registry 统一工具契约和异常结果，context 携带 cwd、权限、session 等运行时边界，permission manager 在写盘或执行命令前作出判定。它们共同构成“模型可以提出意图，但不能越过安全边界”的约束。

#### `SessionData` 与 readiness 报告

session 保存消息、checkpoint 和 workspace 元数据，支持 replay/rewind；readiness 是独立的只读诊断接口，向人和脚本说明当前是 ready、warning/mock 还是 blocked。两者都把运行时状态转化为可检查证据。

### 当前核心流程

```text
entry
  -> model adapter
  -> agent_loop
       -> turn_kernel 决策
       -> ToolRegistry / workspace / permissions
       -> tool_result 回到消息历史
  -> assistant final
  -> session save + replay
  -> readiness / release gate
```

## 对应核心文档

参考项目路径：`D:\JavaProject\MiniCode-Python-main`

- `Docs/Documentation/STRUCTURE.md`
  - 真实项目按入口、编排、工具、TUI、模型、上下文、memory、session、权限、MCP、日志和控制论分层。
  - 明确指出 cybernetic 是可选性能扩展，核心路径不应依赖它。
- `minicode/agent_loop.py`、`minicode/turn_kernel.py`
  - 对照 Lite 的最小 loop/policy 分离，理解真实项目的 fallback、压缩、任务图和预算状态属于增量复杂度。
- `minicode/tooling.py`、`minicode/permissions.py`、`minicode/session.py`、`minicode/readiness.py`
  - 对照统一工具结果、安全边界、持久化证据和机器可读诊断的共同契约。
- `tests/test_agent_loop.py`、`tests/test_tools.py`、`tests/test_session.py`
  - 迁移 scripted model、fake tool、tmp workspace、权限替身和失败路径测试思想。

## 学习产出

### 新增代码

- `tests/test_architecture_review.py`
  - 检查架构笔记仍包含核心分层、模块映射和依赖方向。

### 新增文档

- `ARCHITECTURE_NOTES.md`
  - 记录 Lite 与真实项目的分层地图、六个重点模块对照、数据流、测试迁移和后置项。
- `docs/stage-summaries/stage-17-architecture-review.md`
  - 本阶段的教学总结和面试题库。

### 本阶段最终能力

完成后，项目已经具备：

- 能从入口、模型、loop、工具、安全、session 到 readiness 解释完整 harness 链路。
- 能区分核心路径、产品面和高级优化层，知道哪些能力应保持可选。
- 能用测试替身和临时工作区复现真实项目中的主要测试策略。

## 测试验证

执行的验证命令：

```powershell
python -m pytest -q
python -m minicode_lite /readiness --json
python -m minicode_lite "请分析本项目的核心入口和工具链"
python -m minicode_lite /session-replay latest
```

验证重点：

- 全量测试继续保护前 16 个阶段的最小闭环。
- readiness JSON 仍满足 `schema_version/status/mode/checks` 契约。
- headless 能在离线 mock 模式下完成一次任务并保存 session。
- replay 能从刚保存的 session 读出用户输入、模型步骤、工具结果和最终回答。
- 架构文档契约测试保护核心模块映射和依赖方向。

## 和真实 MiniCode-Python 的差异

### 保留的设计

- 统一的 `ModelAdapter`/`AgentStep` 抽象，loop 不依赖 provider SDK。
- loop 与 turn policy 分离。
- registry/context/result 的工具契约。
- workspace/permissions 的副作用边界。
- session/replay/checkpoint 和 readiness 的可观察证据。

### 简化的设计

- Lite 只有少量文件工具、单进程同步 loop、JSON session 快照和轻量 memory。
- Lite 的 readiness 只做本地四项检查，release gate 只验证离线发布证据。
- REPL 是同步文本入口，没有完整 alt-screen TUI 和增量渲染。

### 后续再实现的设计

- provider streaming、模型热切换和重试策略。
- context compaction、分层/向量 memory 和更复杂任务图。
- MCP stdio、完整技能生态、TUI 渲染和 cybernetic 控制器。
- 结构检查、artifact bundle、跨平台 CI 和签名制品。

## 常见误区

- 误区：真实项目文件多，所以 Lite 文件越多越接近正确。
  - 纠正：先守住 `entry -> agent_loop -> tools -> session`，复杂模块必须有消费者和测试证据。
- 误区：`turn_kernel` 应该直接执行工具。
  - 纠正：kernel 只作策略判定，loop/registry 承担真实副作用。
- 误区：readiness 的 warning 等于不可运行。
  - 纠正：Lite 的 `warning/mock` 是明确支持的离线模式，blocked 才是基础条件缺失。
- 误区：session 只保存最终文本即可 replay。
  - 纠正：工具调用和结果也是事实证据，必须保留在消息历史中。
- 误区：安全边界属于 TUI 审批提示。
  - 纠正：权限检查必须位于工具执行路径，headless 默认拒绝也要可测试。

## 复习提示

重点重新理解：

- 为什么模型适配器、loop、工具 registry 和权限必须保持方向清晰。
- 为什么真实项目的 context、memory、TUI、MCP、控制论可以作为可选层。
- 为什么架构回顾仍需要 replay、失败路径和文档契约测试。

## 面试高频问题与参考答案

### 1. MiniCode Lite 的最小核心路径是什么？

**参考答案：** 最小核心路径是 `entry -> model adapter -> agent loop -> tool registry -> workspace/permissions -> session`。入口接收任务，模型适配器产出统一的 assistant/tool step，loop 编排调用，registry 执行工具，workspace 和权限限制副作用，session 保存可回放证据。readiness 和 release gate 在路径外侧提供观察和交付判断。

### 2. 为什么 `agent_loop.py` 和 `turn_kernel.py` 要分开？

**参考答案：** loop 负责消息写入、工具执行等副作用，kernel 负责 phase、重试、verification、widening 和停止原因。分开后策略可以用纯状态测试，工具执行仍有明确边界；如果合并，复杂分支会隐藏状态变化，也更难排查空回答或超步数问题。

### 3. Lite 与真实项目的 `ToolRegistry` 共同解决什么问题？

**参考答案：** 两者都把工具名称、输入校验、上下文、结果和异常处理统一起来，让 loop 不需要为每个工具写特殊分支。真实项目进一步增加 capability、输出裁剪、后台任务和日志，因为工具规模更大；Lite 保留最小契约以便教学和离线测试。

### 4. 权限边界为什么不能只放在 CLI 或 TUI？

**参考答案：** 模型和工具也可能绕过界面直接执行，headless、测试和未来 API 入口更没有人工提示。因此路径越界、编辑审批和危险命令判定必须在工具实际执行前统一检查。界面只负责展示或收集决定，不能成为唯一安全防线。

### 5. 为什么 session 要保存工具调用和结果，而不只保存最终回答？

**参考答案：** 最终回答无法证明模型到底读了什么、工具是否失败、写入前有没有 checkpoint。保留完整消息历史才能 replay 真实过程，保留 checkpoint 才能 rewind；这让 session 成为可诊断的运行证据，而不是聊天记录摘要。

### 6. 场景题：headless 返回成功，但 `/session-replay latest` 没有工具结果，如何排查？

**参考答案：** 先确认本轮是否真的触发了 tool call，再检查 loop 是否把 `tool_result` 写入返回消息；然后检查 headless 是否把返回历史赋给 session.messages，最后确认 save_session 使用了同一 workspace 和 session 目录。可以用 scripted model 固定产生一次工具调用，再运行集成测试逐层断言。

### 7. 取舍题：为什么不在阶段 17 复制真实项目的完整 TUI、MCP 和控制论？

**参考答案：** 它们需要额外协议、状态和外部依赖，当前最小闭环没有消费者。过早复制会增加维护成本，却不能提高核心 harness 的可理解性。正确做法是保留清晰扩展点和架构记录，等真实需求、接口和独立测试都出现后再接入。

### 8. 如何验证架构回顾没有脱离实际代码？

**参考答案：** 先运行全量 pytest 和 release gate，再用 headless 在 mock 模式跑一轮并用 session replay 检查真实消息流；同时用文档契约测试确认笔记列出了实际核心模块和依赖方向。这样文档结论既有源码对照，也有运行时证据，而不是只写静态观点。

## 下一阶段衔接

阶段 17 解决了：

```text
知道当前 Lite 的核心链路、真实项目的扩展分层，以及哪些复杂度应后置
```

后续不再按路线机械堆功能，而应选择一个有明确需求的扩展做小范围增强，并继续遵守“最小闭环、对照真实模块、测试验证”的节奏。

