# 阶段 01：核心类型和脚本化模型学习总结

## 主题

本阶段的主题是：先定义 MiniCode Lite 里“模型和 harness 之间怎么说话”。

大白话讲，阶段 0 只是让程序能启动；阶段 1 开始进入 agent 的核心世界。但我们还不接真实大模型，也不执行真实工具，而是先规定一套共同语言：

- 用户消息长什么样？
- 模型回复长什么样？
- 模型想调用工具时该怎么表达？
- 测试里怎样假装有一个模型？

这套共同语言就是 `types.py`，假模型就是 `mock_model.py`。

## 问题是什么

### 为什么阶段 1 不直接写 agent loop

agent loop 的职责是反复做这件事：

```text
问模型 -> 看模型是回复还是要工具 -> 执行工具 -> 把结果再给模型 -> 得到最终回答
```

但是在写 loop 之前，必须先确定模型返回的数据形状。如果没有统一类型，后面会变成这样：

- OpenAI 返回一种结构；
- Anthropic 返回一种结构；
- mock model 返回一种结构；
- 测试里又手写另一种结构；
- agent loop 到处都是 provider 细节判断。

这会让 harness 很难测，也很难扩展。

所以阶段 1 要解决的是“模型输出标准化”的问题。

### 本阶段具体要解决的问题

1. 怎么表示一条对话消息。
2. 怎么表示一次工具调用请求。
3. 怎么表示模型的一步输出。
4. 怎么为后续 stop reason、pause、max tokens 等诊断信息预留位置。
5. 怎么写一个可控的假模型，让测试不依赖真实 API。

## 解决方案

### 最小解决方案

本阶段新增两个核心模块：

- `minicode_lite/types.py`
- `minicode_lite/mock_model.py`

`types.py` 负责定义数据结构：

- `ChatMessage`
- `ToolCall`
- `StepDiagnostics`
- `AgentStep`
- `ModelAdapter`

`mock_model.py` 负责提供两个模型替身：

- `ScriptedModel`
- `MockModelAdapter`

### 为什么这就是最小闭环

阶段 1 的最小闭环不是“模型调用工具并执行”，而是：

```text
输入 messages -> 模型 next() -> 返回 AgentStep
```

其中 `AgentStep` 只有两种主要形态：

```text
assistant：模型直接说话
tool_calls：模型请求调用工具
```

只要这两种形态稳定，阶段 2 就可以实现工具注册表，阶段 3 就可以实现 agent loop。

## 工作原理

### 你要建立的心智模型

把模型想象成一个只会返回“下一步动作”的角色。

它每次看到 messages 后，只能做两类事：

1. 直接回答：

```python
AgentStep(type="assistant", content="done")
```

2. 请求工具：

```python
AgentStep(
    type="tool_calls",
    calls=[
        {
            "id": "call-1",
            "toolName": "read_file",
            "input": {"path": "demo.txt"},
        }
    ],
)
```

注意：模型自己不执行工具。它只是说“我想调用 `read_file`，参数是 `demo.txt`”。真正执行工具是后面 agent loop 和 tool registry 的责任。

这就是 harness 的一个重要边界：

```text
模型负责决定下一步想做什么。
harness 负责执行、记录、验证和继续推进。
```

### 核心对象解释

#### `ChatMessage`

`ChatMessage` 表示对话流里的一条消息。

目前支持这些角色：

- `system`：系统提示。
- `user`：用户输入。
- `assistant`：模型最终或普通回复。
- `assistant_progress`：模型进度信息，后续阶段会用。
- `assistant_tool_call`：模型发出的工具调用记录。
- `tool_result`：工具执行后的结果。

大白话讲，`messages` 就像流水账：谁说了什么、工具有没有被调用、工具结果是什么，都按顺序放进去。

#### `ToolCall`

`ToolCall` 表示模型想调用工具。

它有三个关键字段：

- `id`：这次工具调用的编号。
- `toolName`：工具名，比如 `read_file`。
- `input`：工具参数，比如 `{"path": "demo.txt"}`。

后面阶段 2 的 `ToolRegistry` 会根据 `toolName` 找到真正的工具函数。

#### `AgentStep`

`AgentStep` 是模型每一步的统一返回值。

它最重要的字段是：

- `type="assistant"`：模型直接输出文本。
- `type="tool_calls"`：模型请求调用工具。
- `content`：文本内容。
- `calls`：工具调用列表。
- `diagnostics`：诊断信息，给后续 pause、max tokens、block reason 使用。

这一步非常关键。真实 provider 的响应可能很复杂，但进入我们自己的 harness 后，都应该被适配成 `AgentStep`。

#### `StepDiagnostics`

`StepDiagnostics` 目前看起来还用得不多，但它是在给后面留位置。

例如真实 MiniCode 里会遇到：

- 模型空响应；
- `pause_turn`；
- `max_tokens`；
- thinking block 被忽略；
- provider stop reason。

这些都不能散落在字符串里，最好放进结构化对象。

#### `ModelAdapter`

`ModelAdapter` 是一个协议：只要一个对象有 `next(messages, ...) -> AgentStep` 方法，它就可以被当成模型。

这让真实模型、mock 模型、脚本化模型都可以站在同一个接口后面。

### `ScriptedModel` 怎么工作

`ScriptedModel` 是测试专用模型。

你提前给它一组步骤：

```python
ScriptedModel([
    AgentStep(type="tool_calls", calls=[...]),
    AgentStep(type="assistant", content="done"),
])
```

然后每调用一次 `next()`，它就按顺序吐出下一步。

这对测试特别重要。因为真实模型每次回答可能不一样，但测试需要确定性。你要测 agent loop，就必须能精确控制：

```text
第一次模型说要调用工具
第二次模型说 done
```

如果步骤用完了，`ScriptedModel` 会抛出清晰错误：

```text
ScriptedModel has no step 2
```

这比测试莫名其妙失败要好很多。

### `MockModelAdapter` 怎么工作

`MockModelAdapter` 是一个非常小的本地模型替身。

它现在支持三种情况：

1. 普通输入：

```text
hello
```

返回：

```text
MiniCode Lite mock model received your message.
```

2. 读文件快捷输入：

```text
/read demo.txt
```

返回一个工具调用：

```python
AgentStep(
    type="tool_calls",
    calls=[
        {
            "id": "mock-read-1",
            "toolName": "read_file",
            "input": {"path": "demo.txt"},
        }
    ],
)
```

3. 如果 messages 里已经有 `tool_result`：

它会把工具结果整理成 assistant 文本。

这模拟了真实 agent loop 里的第二轮模型调用：

```text
模型请求读文件 -> 工具返回文件内容 -> 模型总结文件内容
```

虽然阶段 1 还没有工具执行，但数据形状已经先准备好了。

### 当前核心流程

```text
messages
  -> ModelAdapter.next(messages)
  -> AgentStep(type="assistant")

或

messages
  -> ModelAdapter.next(messages)
  -> AgentStep(type="tool_calls", calls=[...])
```

阶段 1 到这里就停住。它只负责让“模型想做什么”变清楚，不负责真正执行。

## 对应核心文档

参考项目路径：

- `D:\JavaProject\MiniCode-Python-main`

本阶段对应的真实 MiniCode-Python 模块和理解重点：

- `minicode/types.py`
  - 学习真实项目如何定义 `ChatMessage`、`ToolCall`、`AgentStep`、`ModelAdapter`。
  - 重点理解：agent loop 不直接吃 provider 原始响应，而是吃统一后的 `AgentStep`。
- `minicode/mock_model.py`
  - 学习 mock model 如何让本地测试脱离真实大模型。
  - 重点理解：测试 harness 需要确定性。
- `tests/test_agent_loop.py`
  - 观察真实项目如何用 `ScriptedModel` 驱动 loop 测试。
  - 先不要求看懂整个 agent loop，只看“模型第一步返回工具调用，第二步返回 done”这种测试套路。

## 学习产出

### 新增代码

- `minicode_lite/types.py`
  - 定义核心消息、工具调用、模型步骤和模型协议。
- `minicode_lite/mock_model.py`
  - 实现 `ScriptedModel`。
  - 实现 `MockModelAdapter`。

### 新增测试

- `tests/test_types.py`
  - 验证 `ChatMessage` 和 `ToolCall` 是普通数据结构。
  - 验证 `AgentStep` 能表达 assistant 和 tool calls。
  - 验证 `StepDiagnostics` 的默认列表互不共享。
- `tests/test_mock_model.py`
  - 验证普通输入返回 assistant。
  - 验证 `/read demo.txt` 转成 `read_file` 工具调用。
  - 验证工具结果能被整理为 assistant 文本。
  - 验证 `ScriptedModel` 按顺序返回步骤。
  - 验证脚本耗尽时错误清晰。

### 新增文档

- `docs/stage-summaries/stage-01-core-types-and-scripted-model.md`
  - 当前这份阶段 1 复习文档。

### 本阶段最终能力

完成后，项目已经具备：

- 一套稳定的模型输出数据结构。
- 一个可被后续测试复用的脚本化模型。
- 一个能模拟简单 assistant 回复和工具调用的 mock 模型。
- 为阶段 2 工具注册表、阶段 3 agent loop 准备好了接口。

## 测试验证

执行的验证命令：

```powershell
python -m pytest -q
```

验证结果：

- `11 passed`

重点验证行为：

- `AgentStep(type="assistant")` 可以表达普通文本回复。
- `AgentStep(type="tool_calls")` 可以表达模型想调用工具。
- `StepDiagnostics` 的 `blockTypes`、`ignoredBlockTypes` 不会多个实例共享同一个列表。
- `MockModelAdapter` 可以把 `/read demo.txt` 转为 `read_file` 工具调用。
- `ScriptedModel` 能让测试精确控制模型每一步输出。

## 和真实 MiniCode-Python 的差异

### 保留的设计

- 保留 `ChatMessage`、`ToolCall`、`AgentStep`、`StepDiagnostics`、`ModelAdapter` 的核心思想。
- 保留“provider 输出先适配成统一 `AgentStep`，再交给 harness”的边界。
- 保留 mock/scripted model 用于测试的做法。

### 简化的设计

真实 MiniCode-Python 的模型层会处理更多情况：

- OpenAI/Anthropic provider 适配；
- streaming 输出；
- stop reason；
- content block；
- tool use id；
- provider 错误；
- fallback model；
- runtime event。

阶段 1 全部不做。我们只保留最核心的问题：

```text
模型下一步到底是说话，还是要工具？
```

### 后续再实现的设计

- 阶段 2：让 `toolName` 真正找到工具并执行。
- 阶段 3：让 `AgentStep(type="tool_calls")` 进入 agent loop。
- 阶段 9：引入配置和模型注册表。
- 阶段 13：扩展 turn kernel、phase、verification、widening。

## 常见误区

- 误区 1：觉得类型只是形式，晚点写也行。
  - 不行。类型是 harness 的协议，协议不稳，后面所有模块都要返工。
- 误区 2：觉得 mock model 没有智能，所以没用。
  - mock model 的价值不是智能，而是稳定。测试需要可控，不需要聪明。
- 误区 3：模型调用工具等于工具已经执行。
  - 不是。模型只是提出工具调用请求，真正执行要等阶段 2 和阶段 3。
- 误区 4：直接在 agent loop 里判断 `/read` 就好。
  - 这样会把模型决策、命令解析、工具执行混在一起。阶段 1 先把模型输出边界独立出来。

## 复习提示

下次复习时，重点理解：

- `AgentStep` 为什么是模型层和 harness 层之间的分界线。
- `assistant` 和 `tool_calls` 两种 step 分别代表什么。
- `ScriptedModel` 为什么能让 agent loop 测试变简单。
- `ModelAdapter` 为什么要设计成协议，而不是固定某个具体类。

可以尝试自己回答：

- 如果模型想读文件，它应该返回什么 `AgentStep`？
- 如果工具执行完了，messages 里应该追加什么角色的消息？
- 为什么不让 agent loop 直接解析 OpenAI 或 Anthropic 的原始响应？
- `ScriptedModel` 和 `MockModelAdapter` 有什么区别？

## 下一阶段衔接

阶段 1 定义了“模型怎么表达工具调用”。阶段 2 要解决下一个问题：

```text
模型说要调用 read_file，那 harness 怎么根据 read_file 找到真正的工具函数？
```

也就是说：

- 阶段 1 解决“模型请求工具”的数据形状。
- 阶段 2 解决“工具如何注册、查找、校验、执行”。
- 阶段 3 再把模型和工具接成完整循环。

阶段 1 的产物会这样支撑阶段 2：

- `ToolCall.toolName` 会成为 `ToolRegistry.find(name)` 的查找 key。
- `ToolCall.input` 会成为工具 validator 和 runner 的输入。
- `ScriptedModel` 会在后续阶段继续用来模拟模型发起工具调用。
