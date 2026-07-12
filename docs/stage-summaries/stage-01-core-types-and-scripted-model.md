# 阶段 01：核心类型和脚本化模型学习总结

## 主题

本阶段学习 MiniCode harness 的模型边界：先不接真实大模型，而是用统一的核心类型和可控的 mock/scripted model 建立后续测试基础。

## 问题是什么

如果没有统一的模型输出形状，后续 agent loop、工具注册表、session replay 都会直接依赖某个 provider 的细节，测试也会变得不稳定。

本阶段要解决的具体问题：

- 用 `AgentStep` 把 assistant 文本和工具调用统一成同一种模型返回对象。
- 用 `ScriptedModel` 让测试可以精确控制模型每一步返回什么。
- 用 `MockModelAdapter` 提供一个最小的本地模型替身，先跑通 prompt -> assistant / tool call 的最短路径。

## 解决方案

本阶段采用的最小实现方案：

- 新增 `minicode_lite/types.py`，定义 `ChatMessage`、`ToolCall`、`StepDiagnostics`、`AgentStep`、`ModelAdapter`。
- 新增 `minicode_lite/mock_model.py`，实现 `ScriptedModel` 和 `MockModelAdapter`。
- 新增类型和 mock model 测试，验证数据形状、默认值、脚本顺序、`/read` 到 `read_file` 工具调用的转换。

保留的能力：

- `AgentStep(type="assistant")` 表示最终或进度文本。
- `AgentStep(type="tool_calls")` 表示模型请求执行工具。
- `ScriptedModel` 记录调用次数和收到的 messages，方便后续 agent loop 测试断言。

暂时简化或后置的能力：

- 不实现真实 provider。
- 不实现工具注册、工具执行和 agent loop。
- 不实现 streaming、复杂 diagnostics、runtime event 和 turn kernel。

## 工作原理

核心流程：

```text
用户消息 -> ModelAdapter.next -> AgentStep(assistant 或 tool_calls)
```

关键对象：

- `ChatMessage`：保存 system/user/assistant/tool_result 等对话消息。
- `ToolCall`：保存一次工具调用的 id、工具名和输入。
- `AgentStep`：模型每一步的统一返回值。
- `StepDiagnostics`：为后续记录 stop reason 和 block 信息预留位置。
- `ScriptedModel`：按预设步骤返回 `AgentStep`，测试用它驱动确定性行为。
- `MockModelAdapter`：根据简单输入返回固定 assistant 或 `read_file` 工具调用。

数据如何流动：

- 普通用户输入会让 `MockModelAdapter` 返回 assistant 文本。
- `/read demo.txt` 会让 `MockModelAdapter` 返回 `read_file` 工具调用。
- 当 messages 中已有 `tool_result` 时，`MockModelAdapter` 会把工具结果整理成 assistant 文本。

## 对应核心文档

参考项目路径：

- `D:\JavaProject\MiniCode-Python-main`

本阶段对照阅读的真实模块、测试或文档：

- `minicode/types.py`：理解真实项目如何用 `AgentStep` 抽象 assistant 和 tool calls。
- `minicode/mock_model.py`：理解为什么测试 harness 不直接依赖真实 provider。
- `tests/test_agent_loop.py`：观察真实测试如何用 `ScriptedModel` 驱动 agent loop。
- `MINICODE_HARNESS_LEARNING_PLAN.md`：确认阶段 1 的范围和验收要求。

## 学习产出

新增或修改的代码：

- `minicode_lite/types.py`：核心类型和模型协议。
- `minicode_lite/mock_model.py`：脚本化模型和最小 mock model。

新增或修改的测试：

- `tests/test_types.py`：验证消息、工具调用、步骤对象和 diagnostics 默认值。
- `tests/test_mock_model.py`：验证普通 assistant、`/read` 工具调用、工具结果总结、脚本顺序和耗尽错误。

新增或修改的文档：

- `docs/stage-summaries/stage-01-core-types-and-scripted-model.md`：阶段 1 学习总结。

本阶段最终具备的能力：

- 可以用统一数据结构描述模型输出。
- 可以用可控模型替身编写后续 harness 测试。

## 测试验证

执行的验证命令：

```powershell
python -m pytest -q
```

验证结果：

- `11 passed`

重点验证行为：

- `AgentStep` 可以表达 assistant 文本和工具调用。
- `StepDiagnostics` 的默认列表互不共享。
- `MockModelAdapter` 可以把 `/read demo.txt` 转为 `read_file` 工具调用。
- `ScriptedModel` 按顺序返回步骤，并在脚本耗尽时给出清晰错误。

## 和真实 MiniCode-Python 的差异

保留的设计：

- 保留 `ChatMessage`、`ToolCall`、`AgentStep`、`StepDiagnostics`、`ModelAdapter` 的核心形状。
- 保留模型输出先抽象为 `AgentStep`，再交给 loop 消费的边界。

简化的设计：

- `MockModelAdapter` 只支持普通 assistant、`/read` 和工具结果总结。
- `ScriptedModel` 放在本项目正式模块中，便于阶段学习复用。
- 没有实现真实项目里的更多 slash command 和复杂工具调用。

后续再实现的设计：

- 阶段 2 实现工具注册表。
- 阶段 3 实现最小 agent loop。
- 阶段 13 再扩展 turn kernel、phase、verification、widening 等策略。

## 复习提示

下次复习时，重点重新理解：

- 为什么 agent loop 不应该直接依赖 provider 返回结构。
- `assistant` 和 `tool_calls` 两类 `AgentStep` 如何支撑后续循环。
- 为什么 `ScriptedModel` 是测试 harness 的核心工具。

可以尝试自己回答：

- 如果模型想读文件，它应该返回什么数据？
- 如果工具执行完了，下一次模型输入里应该多出什么消息？
- 为什么真实 provider 应该被包在 `ModelAdapter` 后面？

## 下一阶段衔接

本阶段产物如何支撑下一阶段：

- 阶段 2 可以让 `ToolCall.toolName` 对接 `ToolRegistry`。
- `ScriptedModel` 可以在阶段 3 直接驱动 model -> tool -> model -> final 的闭环测试。

下一阶段开始前要确认：

- `AgentStep(type="tool_calls")` 的 `calls` 字段已稳定。
- `MockModelAdapter` 的 `/read` 工具调用输入格式和未来 `read_file` 工具保持一致。
