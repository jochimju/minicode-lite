# 阶段 15：轻量交互式 REPL 学习总结

## 主题

本阶段把只能“一次输入、一次退出”的 headless harness 变成可以连续对话的终端 REPL。大白话讲，前面的模块已经是一台能工作的发动机，本阶段增加的是方向盘、仪表和连续驾驶的入口：用户输入一行，系统判断它是本地命令还是 agent 任务，并把工具开始、工具结果和最终回答按发生顺序显示出来。

## 问题是什么

headless 适合脚本和测试，却不适合观察多轮工作过程。若每次输入都重新启动，用户看不到同一会话中的消息累积，也难以理解工具为何开始、何时结束、失败后留下了什么状态。

本阶段解决四个问题：输入如何分流；多轮消息和 session 如何持续；工具生命周期如何进入 transcript；退出或异常时如何处理仍处于 running 的工具。

## 解决方案

- `tui/input_handler.py` 用纯函数把输入分类为 `empty`、`exit`、`local` 或 `agent`。
- `Repl` 持有 workspace、工具注册表、权限、模型、消息、session 和 transcript，在多轮输入之间复用这些状态。
- 本地命令继续交给 `try_handle_local_command`，普通输入交给 `run_agent_turn`。
- `ToolLifecycle` 用工具调用 ID 配对 start/result，turn 结束时用 `finalize` 把悬挂调用标为 error。
- `python -m minicode_lite --repl` 和 `minicode-lite-repl` 提供真实可启动入口。

当前方案已经形成可用闭环，但没有引入 raw mode、alt-screen、滚动区域、主题或 Markdown 渲染。这些属于完整 TUI 的显示复杂度，不是理解 harness 交互面的必要条件。

## 工作原理

### 心智模型

REPL 不是新的 agent 核心，而是一个协调层。它负责接收输入、选择已有能力、展示回调事件并保存状态；模型推理、工具执行、权限和 session 仍由原模块负责。这样 UI 可以替换，而 harness 核心不必重写。

### 核心对象

#### `InputEvent` / `classify_input`

它们建立输入边界。`/exit`、`/quit`、`/q` 是 REPL 自己处理的退出事件；其他斜杠输入进入本地命令；普通文本进入 agent。纯函数设计使分流无需启动模型即可测试。

#### `Repl`

它是交互表面的会话协调器。首次 agent 输入时才加载配置和模型，因此 `/tools` 等本地命令仍可离线运行。每轮 agent 完成后，消息被写回同一个 session，支持后续 `/session`、replay 和 checkpoint 命令。

#### `TranscriptEntry` / `ToolLifecycle`

`TranscriptEntry` 是展示层事件，`ToolLifecycle` 管理 `running -> complete/error` 状态。结果找不到对应 start、工具名不匹配或退出时仍未完成，都不能静默当作成功。

### 当前核心流程

```text
terminal line
  -> classify_input
  -> exit: stop loop
  -> local: try_handle_local_command -> print result
  -> agent: append user message -> run_agent_turn
       -> on_tool_start -> transcript running + terminal output
       -> on_tool_result -> transcript complete/error + terminal output
       -> on_assistant_message -> transcript assistant + terminal output
  -> save_session
```

## 对应核心文档

参考项目：`D:\JavaProject\MiniCode-Python-main`

- `minicode/tty_app.py`：对照主循环、session 生命周期和退出清理责任。
- `minicode/tui/input_handler.py`：理解输入解析和命令分流应与 agent 执行分离。
- `minicode/tui/tool_lifecycle.py`：理解工具 start/result 配对及未完成工具清理。
- `tests/test_tty_app.py`：参考可注入状态和展示辅助函数的测试方式。

## 学习产出

- `minicode_lite/repl.py`：轻量多轮 REPL 与函数式入口。
- `minicode_lite/tty_app.py`：与真实项目命名对应的兼容入口。
- `minicode_lite/tui/input_handler.py`：输入事件解析。
- `minicode_lite/tui/tool_lifecycle.py`：工具生命周期和 transcript 状态。
- `tests/test_repl_stage15.py`：输入分流、本地命令、agent、多工具事件顺序和悬挂清理测试。
- `main.py`、`pyproject.toml`、`README.md`：可启动入口与使用说明。

## 测试验证

执行：

```powershell
python -m pytest -q
```

重点验证：本地命令不会提前创建模型；工具事件严格先 start、再 result、最后 assistant；session 保存最终消息；EOF 和 `/exit` 都能退出；悬挂 running 工具会转为 error。

2026-07-20 的全量结果为 `171 passed, 1 skipped`；跳过项仍是需要显式启用的 live Qwen 测试。

## 和真实 MiniCode-Python 的差异

保留了输入分流、持续 session、工具生命周期、退出清理和 callback 驱动 transcript。简化了并发 agent 线程、raw keyboard event、权限弹窗、全屏重绘、滚动、窗口 resize、主题、Markdown 和流式 token。当前 REPL 是同步行模式，适合学习和测试；真实 TUI 是事件驱动产品界面，负责更多终端兼容性和并发状态。

## 常见误区

- 误区：REPL 应重新实现 agent loop。纠正：REPL 只做协调和展示，核心执行必须复用 `run_agent_turn`。
- 误区：打印工具结果就等于有生命周期。纠正：必须用调用 ID 关联 start/result，并显式处理没有结果的 running 状态。
- 误区：所有斜杠命令都要发给模型。纠正：本地产品命令应先分流，避免网络调用和不必要 token 消耗。
- 误区：全屏界面越复杂越能说明 harness。纠正：本阶段要学的是输入、状态和事件流，而不是终端渲染技巧。

## 复习提示

重点理解：为什么模型延迟创建；为什么 transcript 是消息历史的展示投影而不是新的权威状态；为什么 tool start/result 需要 ID；为什么退出清理属于 UI 生命周期的一部分。

自测问题：如果 `/tools` 触发了 provider 请求，边界错在哪里？如果只有 tool start 没有 result，replay 应显示什么？多轮 REPL 为什么必须复用 messages 和 session？

## 面试高频问题与参考答案

### 1. REPL 在 agent harness 中的职责是什么？

**参考答案：** REPL 是输入和展示协调层，不是推理核心。它读取用户输入、区分本地命令与 agent 任务、调用已有 loop、展示生命周期事件并保存会话；模型适配、工具执行、权限和策略仍由各自模块负责。

### 2. 为什么输入解析要做成纯函数？

**参考答案：** 因为分类规则不需要模型、磁盘或终端状态。纯函数可直接覆盖空输入、退出别名、斜杠命令和普通任务，减少主循环分支，也避免测试 REPL 时必须启动完整 runtime。

### 3. 一条普通输入的数据如何流动？

**参考答案：** 输入先被分类为 agent，随后追加为 user message；`run_agent_turn` 调用模型并可能执行工具；回调把 tool start、tool result 和 assistant 依次写入展示 transcript；最终消息替换 REPL 当前历史，并保存到同一个 session。

### 4. 为什么本阶段选择同步行模式而不是完整全屏 TUI？

**参考答案：** 当前学习目标是验证交互闭环和生命周期，而不是解决终端渲染。同步行模式已经覆盖输入分流、连续状态、工具事件和退出清理，测试稳定且跨平台；raw mode、重绘和后台线程会增加大量与 harness 主线无关的复杂度。

### 5. 工具调用为什么要有 running 状态？

**参考答案：** start 和 result 可能跨越一段执行时间，界面需要表达“已发起但未结束”。如果程序退出、回调丢失或异常中断，running 不能被误认为成功，因此 `finalize` 会把它转换成 error，保留真实故障事实。

### 6. 如何测试 REPL 而不调用真实模型？

**参考答案：** 注入 `ScriptedModel` 和内存输出流，使用固定输入序列驱动主循环。断言输出顺序、模型收到的消息、session 最终状态和 transcript 事件即可；这避免网络、API key、终端交互和时间不确定性。

### 7. 场景题：终端打印了 tool start，但没有 tool result，如何排查？

**参考答案：** 先检查 agent loop 是否执行到工具回调，再检查工具是否抛出未转换异常，然后核对 result 回调的工具名和调用 ID，最后确认退出路径是否执行 `finalize`。即使根因未修复，session 或 transcript 也应把该调用标成 error，而不是继续显示 running。

### 8. REPL 与 headless 的主要差异是什么？

**参考答案：** headless 面向一次性脚本，只返回最终文本；REPL 面向连续人机交互，复用模型、消息和 session，并实时展示中间工具事件。本质上两者应共享同一套 agent loop 和本地命令，而不是形成两份执行逻辑。

### 9. 为什么本地命令要在创建模型之前执行？

**参考答案：** `/tools`、`/readiness`、`/session` 等命令只读取本地状态，不需要 provider。提前分流能保证离线可用、减少延迟和成本，也防止缺少 API 配置时阻塞诊断命令。

### 10. 当前实现和真实 MiniCode TUI 最大的能力差距是什么？

**参考答案：** 当前是同步单线程行模式；真实项目有 raw key event、后台 agent、流式更新、权限交互、全屏重绘和窗口变化处理。两者共享输入分流和生命周期思想，但产品级 TUI 还必须处理并发、渲染性能和终端兼容性。

## 下一阶段衔接

本阶段已经把各模块组成了可人工操作的连续入口。阶段 16 将把这条路径固定为端到端集成测试和发布检查，覆盖 `prompt -> tool -> final`、session/replay、checkpoint/rewind、readiness 和 Windows 路径行为。
