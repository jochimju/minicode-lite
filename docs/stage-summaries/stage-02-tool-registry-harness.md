# 阶段 02：工具注册表和第一个工具闭环 学习总结

## 主题

本阶段的主题是：建立 MiniCode Lite 的工具 harness，让“模型想调用工具”这件事可以被注册表安全地转换成一次可测试的函数调用。

大白话讲：阶段 1 里我们已经有了“模型会说它想调用哪个工具”的能力，但项目里还没有真正的工具调度台。阶段 2 就是在模型和真实工具之间放一个前台：它负责查工具名、检查输入、执行工具，并把结果统一包装回来。

## 问题是什么

### 为什么要有这个阶段

如果没有工具注册表，agent loop 后面会直接面对一堆散落的函数：不知道有哪些工具、每个工具吃什么输入、工具出错后该怎么继续。真实 agent harness 不能让某个工具的异常直接炸掉整轮对话，所以需要一个统一边界。

### 本阶段具体解决的问题

1. 工具如何被声明和注册。
2. 模型给出工具名和输入后，harness 如何找到并执行对应工具。
3. 未知工具、输入校验失败、工具运行异常如何变成结构化错误结果。

## 解决方案

### 最小解决方案

本阶段新增 `minicode_lite/tooling.py`，只实现四个核心对象：

- `ToolResult`：工具返回给 agent loop 的统一结果。
- `ToolContext`：工具执行时能看到的运行上下文，目前只包含 `cwd` 和少量后续扩展位。
- `ToolDefinition`：一个工具的声明，包括名称、描述、输入 schema、validator 和 run 函数。
- `ToolRegistry`：保存工具列表，按名称查找工具，并执行工具。

### 为什么这个方案足够

阶段 2 的目标不是实现文件读写、权限审批、输出截断或并发调度，而是先跑通最小闭环：

```text
toolName + input
  -> ToolRegistry.execute()
  -> validator(input)
  -> tool.run(parsed, context)
  -> ToolResult
```

只要这个边界稳定，阶段 3 的 agent loop 就可以把模型产出的 tool call 转交给 registry，而不用关心工具内部怎么实现。

## 工作原理

### 心智模型

可以把 `ToolRegistry` 想成 agent 的“工具前台”。模型不能直接进后厨调用任意函数，它只能递交一张单子：工具名和输入。前台检查有没有这个工具，先让 validator 看输入是否合法，再把整理好的输入交给真正的工具函数。

### 核心对象解释

#### `ToolResult`

`ToolResult` 是工具执行的统一出口。成功时 `ok=True`，`output` 是工具结果；失败时 `ok=False`，`output` 是错误说明。后续 agent loop 可以把它直接写成 `tool_result` 消息。

#### `ToolContext`

`ToolContext` 是工具运行时的上下文包。当前最重要的是 `cwd`，后续阶段会逐步接入权限、session 和 runtime。这样工具函数不需要从全局变量里偷状态。

#### `ToolDefinition`

`ToolDefinition` 把“工具是什么”和“怎么运行它”放在一起。`validator` 负责把模型输入变成工具函数能安全消费的数据，`run` 负责真正执行。

#### `ToolRegistry`

`ToolRegistry` 维护工具名到 `ToolDefinition` 的索引。它的 `execute()` 是关键边界：未知工具、校验错误、运行异常都在这里变成 `ToolResult(ok=False)`，避免异常穿透到更外层。

### 当前核心流程

```text
模型产生 ToolCall
  -> ToolRegistry.execute(toolName, input, context)
  -> find(toolName)
  -> validator(input)
  -> run(parsedInput, context)
  -> ToolResult(ok=True/False, output=...)
```

## 对应核心文档

参考项目路径：

- `D:\JavaProject\MiniCode-Python-main`

本阶段对照的真实 MiniCode-Python 模块和理解重点：

- `minicode/tooling.py`
  - 真实项目也把工具声明成 `ToolDefinition`，把结果统一成 `ToolResult`。
  - 真实项目的 `ToolRegistry.execute()` 会保护未知工具、输入校验和运行异常。
  - 真实项目包含输出截断、日志、metadata、read-only/concurrency 等能力，本阶段暂不实现。
- `tests/test_agent_loop.py`
  - 真实测试里用 `echo` 这类假工具驱动 agent loop，说明工具注册表适合作为模型和 loop 之间的测试缝合点。

## 学习产出

### 新增代码

- `minicode_lite/tooling.py`
  - 新增 `ToolResult`、`ToolContext`、`ToolDefinition`、`ToolRegistry`。
  - 支持注册工具、查找工具、执行工具。
  - 将未知工具、validator 异常、run 异常转换为结构化失败结果。

### 新增测试

- `tests/test_tooling.py`
  - 验证已注册工具可以执行。
  - 验证未知工具返回错误结果。
  - 验证 validator 抛错会变成 `ToolResult(ok=False)`。
  - 验证工具运行抛错不会炸掉测试进程。

### 新增文档

- `docs/stage-summaries/stage-02-tool-registry-harness.md`
  - 用于后续复习阶段 2 的工具 harness 心智模型。

### 本阶段最终能力

完成后，项目已经具备：

- 一个可测试的工具注册表。
- 一个统一的工具执行结果结构。
- 一个可以给阶段 3 agent loop 复用的工具调用边界。

## 测试验证

执行的验证命令：

```powershell
python -m pytest -q
```

重点验证行为：

- 已注册 `echo` 工具能被执行并返回输出。
- 未知工具不会抛异常，而是返回 `Unknown tool` 错误。
- validator 的 `ValueError` 会转换为输入校验错误。
- 工具 `run` 的 `RuntimeError` 会转换为工具崩溃错误。

## 和真实 MiniCode-Python 的差异

### 保留的设计

- 保留 `ToolDefinition`、`ToolContext`、`ToolResult`、`ToolRegistry` 这组核心边界。
- 保留“工具异常不穿透到外层 loop”的设计。
- 保留 validator 和 run 分离的设计。

### 简化的设计

- 暂不实现 `ToolMetadata`、能力标签、read-only/concurrency 判断。
- 暂不实现大输出智能截断。
- 暂不接入日志系统。
- 暂不接入权限审批和 session checkpoint。

### 后续再实现的设计

- 阶段 4 会把文件工具挂到 `ToolRegistry` 上。
- 阶段 6 会让 `ToolContext.permissions` 真正参与工具执行。
- 阶段 7/8 会让 `ToolContext.session` 记录会话和 checkpoint。
- 阶段 12 可以补日志和 readiness 诊断。

## 常见误区

- 误区 1：工具注册表就是一个字典。
  - 纠正：字典只负责查找，注册表还负责统一校验、执行和错误边界。
- 误区 2：validator 是可选装饰。
  - 纠正：validator 是模型输入进入工具函数前的安全门，后续真实工具越多，它越重要。
- 误区 3：工具抛异常应该直接暴露。
  - 纠正：agent loop 需要稳定消息流，所以工具异常应转换为 `ToolResult(ok=False)`，再交给模型决定下一步。

## 复习提示

下次复习时，重点理解：

- 为什么工具调用要分成 `validator` 和 `run` 两步。
- 为什么错误也要变成普通的 `ToolResult`。
- 为什么 `ToolContext` 现在很小，但后续会成为权限、session、runtime 的入口。

可以尝试自己回答：

- 如果模型调用了不存在的工具，agent loop 应该继续还是崩溃？
- 为什么 `ToolResult` 不直接返回任意 Python 对象？
- 文件工具接入时，`cwd` 应该从哪里传进来？

## 下一阶段衔接

本阶段解决了：

```text
tool name + input -> validated tool execution -> structured result
```

下一阶段要解决：

```text
model -> tool call -> registry execution -> tool_result message -> model -> final assistant
```

本阶段产物会这样支撑下一阶段：

- `ToolRegistry.execute()` 会成为 agent loop 执行工具调用的唯一入口。
- `ToolResult` 会被转换成 `tool_result` 消息，重新喂给 mock/scripted model。
