# 阶段 03：最小 agent loop 学习总结

## 主题

本阶段的主题是：实现 MiniCode Lite 的最小 agent loop，让一次用户任务可以从模型输出、工具调用、工具结果再回到模型最终回答。

大白话讲：阶段 1 让模型能“说出下一步”，阶段 2 让工具能“被安全调用”，阶段 3 就是把两者串成一条会走路的链。没有 agent loop，模型和工具只是两个分开的零件；有了 loop，harness 才开始像一个真正的 agent。

## 问题是什么

### 为什么要有这个阶段

真实 agent 的核心不是“问模型一次就结束”，而是模型经常需要先调用工具，看见工具结果后再继续推理。比如模型先决定调用 `read_file`，工具返回文件内容后，模型才能给用户总结。agent loop 负责维持这个来回过程，并把每一步都写成可检查的消息。

### 本阶段具体要解决的问题

1. 模型返回 final assistant 时，如何结束本轮任务。
2. 模型返回 tool calls 时，如何写入 `assistant_tool_call`、执行工具、再写入 `tool_result`。
3. 工具结果如何重新进入 messages，让下一次模型调用能看见。
4. 空 assistant 响应如何重试一次，避免一次空输出直接结束。
5. `max_steps` 如何防止模型和工具无限循环。
6. 工具开始、工具结果、assistant 消息如何通过回调暴露给外层界面。

## 解决方案

### 最小解决方案

本阶段新增 `minicode_lite/agent_loop.py`，核心函数是 `run_agent_turn()`：

- 复制输入 messages，避免直接修改调用者传入的列表。
- 在 `max_steps` 范围内调用 `model.next()`。
- 如果模型返回 assistant final，写入 `{"role": "assistant"}` 并结束。
- 如果模型返回 tool calls，逐个写入 `assistant_tool_call`，调用 `ToolRegistry.execute()`，再写入 `tool_result`。
- 如果 assistant 内容为空，追加一条 user nudge 并重试一次；第二次仍为空则给出停止说明。
- 如果超过 `max_steps`，追加一条 assistant 停止说明。
- 在工具生命周期和最终 assistant 输出处触发回调。

### 为什么这个方案足够

阶段 3 只需要跑通 harness 心脏的最小闭环，不需要复制真实 MiniCode 里的 provider fallback、上下文压缩、turn kernel phase、verification guard、TUI transcript 或复杂 runtime 事件。当前实现刻意保持小：它只解决“模型怎么驱动工具、工具结果怎么回到模型”这一条主线。

## 工作原理

### 你要建立的心智模型

可以把 agent loop 想成一个调度员。模型不是直接操作文件或系统，它只交出“下一步计划”：要么回答用户，要么要求调用工具。调度员检查这一步，如果是工具调用，就去工具注册表执行；执行结果不是直接展示完事，而是写回消息流，再让模型继续判断下一步。

### 核心对象解释

#### `run_agent_turn()`

本阶段的主入口。它接收模型、工具注册表、已有 messages 和 cwd，然后负责推进一次 agent turn，直到得到最终 assistant 消息或触发停止条件。

#### `ChatMessage`

消息流里的统一记录格式。本阶段新增使用的关键 role 是：

- `assistant_tool_call`：记录模型要求调用的工具。
- `tool_result`：记录工具执行后的结果。
- `assistant`：记录最终给用户看的回答。
- `assistant_progress`：为后续进度消息保留的轻量入口。

#### `ToolRegistry.execute()`

阶段 2 的产物，在阶段 3 被真正接入 loop。agent loop 不关心具体工具怎么实现，只把 `toolName`、`input` 和 `ToolContext` 交给注册表。

#### 回调函数

`on_tool_start`、`on_tool_result`、`on_assistant_message` 是外层 UI 或 headless 模式观察 loop 的入口。阶段 3 只做最小事件，不引入完整 transcript 系统。

### 当前核心流程

```text
用户 messages
  -> run_agent_turn()
  -> model.next(messages)
  -> AgentStep(type="tool_calls")
  -> 写入 assistant_tool_call
  -> ToolRegistry.execute()
  -> 写入 tool_result
  -> model.next(messages)
  -> AgentStep(type="assistant")
  -> 写入 assistant final
```

空响应流程：

```text
model.next()
  -> assistant content=""
  -> 写入 user nudge
  -> model.next()
  -> final 或 empty fallback
```

## 对应核心文档

参考项目路径：

- `D:\JavaProject\MiniCode-Python-main`

本阶段对照的真实 MiniCode-Python 模块和理解重点：

- `minicode/agent_loop.py`
  - 真实项目也以 `run_agent_turn()` 作为一轮 agent 执行的核心入口。
  - 真实项目会把 tool call 和 tool result 都落到 messages 中，而不是只在内存变量里短暂传递。
  - 真实项目包含大量增强能力，本阶段只保留基础循环和工具执行路径。
- `tests/test_agent_loop.py`
  - 真实项目使用 scripted model 和 fake tool 验证 model -> tool -> model 的闭环。
  - 本项目迁移了这种测试方式，但只保留阶段 3 需要的行为。
- `minicode/turn_kernel.py`
  - 真实项目后续把 phase、verification、widening 等策略拆到 turn kernel。
  - 本阶段只理解它为什么存在，不提前实现。

## 学习产出

### 新增代码

- `minicode_lite/agent_loop.py`
  - 新增 `run_agent_turn()`。
  - 新增工具调用消息写入、工具结果消息写入、空响应重试、`max_steps` 停止和生命周期回调。

### 新增测试

- `tests/test_agent_loop.py`
  - 验证工具调用后能得到最终 assistant。
  - 验证工具结果会进入 messages。
  - 验证空 assistant 响应可以重试一次。
  - 验证重复空响应会停止并给出说明。
  - 验证超过 `max_steps` 会停止。
  - 验证工具和 assistant 回调会被触发。
  - 验证输入 messages 不会被原地修改。

### 新增文档

- `docs/stage-summaries/stage-03-minimal-agent-loop.md`
  - 用于后续复习阶段 3 的 agent loop 心智模型。

### 本阶段最终能力

完成后，项目已经具备：

- 一条可测试的 model -> tool -> model -> final 最小闭环。
- 工具调用和工具结果的结构化消息记录。
- 防止空响应和无限循环的基础保护。
- 可供 CLI、headless、TUI 后续接入的生命周期回调。

## 测试验证

执行的验证命令：

```powershell
python -m pytest tests\test_agent_loop.py -q
python -m pytest -q
```

重点验证行为：

- `ScriptedModel` 先返回 tool call，再返回 final assistant 时，loop 能执行工具并最终结束。
- `ToolResult` 会转换成 `tool_result` 消息，并在下一次模型调用前进入 messages。
- 空 assistant 响应会被 nudge 重试一次。
- `max_steps` 能阻止无限循环。
- `on_tool_start`、`on_tool_result`、`on_assistant_message` 能按顺序触发。

## 和真实 MiniCode-Python 的差异

### 保留的设计

- 保留 `run_agent_turn()` 作为一轮任务的核心入口。
- 保留 `AgentStep(type="assistant")` 和 `AgentStep(type="tool_calls")` 的分支模型。
- 保留工具调用和工具结果都写回 messages 的设计。
- 保留工具生命周期回调这一扩展点。

### 简化的设计

- 不做并发工具执行。
- 不做工具超时控制。
- 不做 provider fallback。
- 不做上下文压缩和 token 预算。
- 不做 turn kernel phase、verification guard 和 widening。
- 不做 session transcript、checkpoint 或 memory 注入。

### 后续再实现的设计

- 阶段 4 会把真实文件工具挂入这个 loop。
- 阶段 5 会让 CLI/headless 调用 `run_agent_turn()`。
- 阶段 7 会把 messages 和 transcript 持久化。
- 阶段 13 会把更多 turn 策略从 loop 中拆到 `turn_kernel.py`。

## 常见误区

- 误区 1：agent loop 只是一个 while 循环。
  - 纠正：它是模型、工具、消息流之间的协议边界。while 只是外壳，真正重要的是每一步如何被记录、回放和测试。
- 误区 2：工具结果可以直接返回给用户。
  - 纠正：工具结果应该先进入 messages，再交给模型决定如何解释或继续行动。
- 误区 3：`max_steps` 是性能优化。
  - 纠正：`max_steps` 首先是安全边界，防止模型不断调用工具或空转。
- 误区 4：空响应可以忽略。
  - 纠正：空响应是模型运行时常见异常状态，loop 应该给一次明确重试机会，并在重复发生时停止。

## 复习提示

下次复习时，重点理解：

- 为什么 `assistant_tool_call` 和 `tool_result` 都要写入 messages。
- 为什么 loop 不应该知道具体工具实现细节。
- 为什么空响应和 `max_steps` 属于 harness 的基本防护。
- 为什么回调是后续 UI/headless 的入口，而不是核心逻辑的一部分。

可以尝试自己回答：

- 如果工具返回 `ok=False`，为什么 loop 仍然应该把它写成 `tool_result` 并继续交给模型？
- 如果不复制输入 messages，会给测试和 session replay 带来什么问题？
- 阶段 4 的 `read_file` 工具接入后，`ToolContext.cwd` 会如何发挥作用？

## 下一阶段衔接

本阶段解决了：

```text
model -> tool call -> registry execution -> tool_result message -> model -> final assistant
```

下一阶段要解决：

```text
agent loop -> workspace boundary -> real file tools -> safe read/write/edit
```

本阶段产物会这样支撑下一阶段：

- 文件工具只需要注册到 `ToolRegistry`，loop 不需要改造。
- `tool_result` 消息已经稳定，文件内容和文件错误都可以用同一种方式返回给模型。
- `ToolContext.cwd` 已经从 loop 传入工具，为阶段 4 的路径边界检查预留入口。
