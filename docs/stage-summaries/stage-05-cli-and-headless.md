# 阶段 05：CLI 和 headless 单轮模式学习总结

## 主题

本阶段的主题是：把前面已经做好的 mock model、agent loop 和文件工具，包装成可以从命令行运行的一轮任务。

大白话讲：
- 阶段 0 到 4 已经有了“脑子”和“手”：mock model 会给出响应，agent loop 会调工具，文件工具会读写工作区。
- 阶段 5 要做的是“入口”：让用户不需要写 Python 测试，也能用 `python -m minicode_lite "hello"` 或 `minicode-lite-headless "hello"` 跑通一轮。

## 问题是什么

### 为什么要有这个阶段

如果没有 CLI/headless，MiniCode Lite 只能在测试里被调用。这样虽然能验证内部模块，却还不是一个可使用的 harness。真实 MiniCode-Python 需要支持命令行、CI、脚本和后续交互界面；这些入口最终都要把用户输入送进同一套 runtime。

headless 的价值在于：它没有交互 UI，只做一次输入、一次运行、一次输出。这个模式最适合学习 harness，因为链路短、状态少、测试容易写。

### 本阶段具体要解决的问题

1. 如何把 prompt 转成 `messages`，再交给 `run_agent_turn`。
2. 如何初始化默认工具注册表和 mock model。
3. 如何从命令行拿到用户输入，并打印最后的 assistant 输出。
4. 如何处理最小本地 slash 命令，例如 `/tools` 和 `/read <path>`。
5. 如何保留阶段 0 的无参 smoke 行为，避免破坏旧入口。

## 解决方案

### 最小解决方案

本阶段采用的最小实现方案：

- 新增 `minicode_lite/headless.py`，提供 `run_headless(prompt, cwd=None)`。
- 新增 `minicode_lite/local_commands.py`，集中处理 `/tools` 和 `/read <path>`。
- 扩展 `minicode_lite/main.py`，支持：
  - 无参数时继续输出 `MiniCode Lite ready`。
  - `--version` 继续输出版本号。
  - 有 prompt 时进入 headless 单轮模式。
- 在 `pyproject.toml` 中新增 `minicode-lite-headless` console script。
- 新增 `tests/test_headless.py` 和 `tests/test_cli_stage5.py`，验证 headless、CLI、slash command 和 `python -m minicode_lite`。

### 为什么这个方案足够

阶段 5 只关心“命令行能跑一轮”。它不做真实模型配置、不做权限审批、不保存 session，也不做 TUI。那些能力会在后续阶段逐步加入。这里先保留 mock model，是为了让测试闭环稳定，不被 API key、网络或真实 provider 行为影响。

## 工作原理

### 你要建立的心智模型

headless 就像一条很短的流水线：

```text
命令行输入
  -> headless 初始化 mock model + 默认工具
  -> 本地 slash 命令分流
  -> agent loop
  -> 最后一条 assistant 消息
  -> stdout
```

它不是新的 agent loop，也不是新的模型系统。它只是把已经存在的内部模块按运行顺序组装起来。

### 核心对象解释

#### `run_headless`

`run_headless` 是非交互单轮运行的核心函数。它接收 prompt，校验非空，创建默认工具注册表和 `MockModelAdapter`，然后调用 `run_agent_turn`。最后，它从返回的消息列表里找到最后一条 assistant 消息作为用户可见输出。

#### `try_handle_local_command`

`try_handle_local_command` 负责处理不需要模型参与的本地命令。比如 `/tools` 只是列工具，`/read demo.txt` 只是调用 `read_file`。这些命令可以直接由 CLI 处理，避免把非常确定的本地操作绕进模型。

#### `main.run`

`main.run` 是主 CLI 的可测试入口。它解析参数，把无参、版本查询和 prompt 三条路径分开。测试直接调用这个函数，不需要每次都启动子进程。

#### `minicode-lite-headless`

`minicode-lite-headless` 是 pyproject 中注册的 console script。它面向“只跑一轮任务并退出”的场景，后续真实模型、session、trace 都可以接在这个入口上。

### 当前核心流程

```text
python -m minicode_lite "hello"
  -> minicode_lite.__main__
  -> main.run
  -> run_headless
  -> MockModelAdapter.next
  -> run_agent_turn
  -> assistant message
  -> print
```

`/read demo.txt` 的直接命令流程：

```text
/read demo.txt
  -> try_handle_local_command
  -> ToolRegistry.execute("read_file")
  -> read_file_tool
  -> workspace path guard
  -> file content
```

## 对应核心文档

参考项目路径：

- `D:\JavaProject\MiniCode-Python-main`

本阶段对照的真实 MiniCode-Python 模块和理解重点：

- `minicode/headless.py`
  - 非交互单轮运行负责初始化 runtime、tools、model、messages。
  - 输出最后一条 assistant 消息，并用退出码表达失败。
- `minicode/main.py`
  - 主入口负责参数解析，以及本地命令和 agent turn 的分流。
  - 真实项目还要处理配置、权限、history、session、TUI 等更多产品层能力。
- `minicode/local_tool_shortcuts.py`
  - slash command 可以映射成工具调用。
  - 本项目阶段 5 只保留 `/tools` 和 `/read`，不提前实现完整命令族。
- `tests/test_headless.py`
  - headless 的测试重点是运行时组件是否正确串联、失败是否可观察。

## 学习产出

### 新增代码

- `minicode_lite/headless.py`
  - 实现 headless 单轮运行函数和 headless CLI 入口。
- `minicode_lite/local_commands.py`
  - 实现 `/tools` 和 `/read <path>` 本地命令分流。
- `minicode_lite/main.py`
  - 从阶段 0 smoke CLI 扩展为可接收 prompt 的主入口。
- `pyproject.toml`
  - 新增 `minicode-lite-headless` console script。

### 新增测试

- `tests/test_headless.py`
  - 验证空 prompt 失败、普通 prompt 返回 mock assistant、`/read` 能读工作区文件。
- `tests/test_cli_stage5.py`
  - 验证主 CLI prompt、`/tools`、`/read` 和 `python -m minicode_lite "hello"`。

### 新增文档

- `docs/stage-summaries/stage-05-cli-and-headless.md`
  - 用于复习阶段 5 的入口设计、数据流和与真实 MiniCode-Python 的差异。

### 本阶段最终能力

完成后，项目已经具备：
- 从 Python API 调用 `run_headless("hello")` 跑一轮任务。
- 从命令行运行 `python -m minicode_lite "hello"`。
- 从主 CLI 运行 `/tools` 查看默认工具。
- 从主 CLI 或 headless 运行 `/read demo.txt` 读取工作区文件。
- 通过 console script 暴露 `minicode-lite` 和 `minicode-lite-headless`。

## 测试验证

执行的验证命令：

```powershell
python -m pytest -q
```

验证结果：
- `40 passed`

重点验证行为：
- 空 prompt 在 headless 中会失败，避免悄悄跑出无意义结果。
- 普通 prompt 会通过 mock model 返回固定 assistant 响应。
- `/read demo.txt` 能经过默认文件工具读取工作区文件。
- `/tools` 能列出阶段 4 注册的默认工具。
- `python -m minicode_lite "hello"` 可以作为真实命令行入口运行。
- 阶段 0 的无参 smoke 输出仍然保留。

## 和真实 MiniCode-Python 的差异

### 保留的设计

- 保留 headless 单轮模式。
- 保留主 CLI 对本地命令和 agent turn 的分流思想。
- 保留“最后 assistant 消息作为最终输出”的简单约定。
- 保留用自动化测试验证 CLI/headless 行为的做法。

### 简化的设计

- 真实 MiniCode-Python 会加载 runtime config，本阶段只使用 `MockModelAdapter`。
- 真实项目会初始化权限、memory、session、logging，本阶段暂不处理。
- 真实 headless 会根据错误内容决定退出码，本阶段只实现空 prompt 的失败路径。
- 真实 CLI 支持大量产品命令，本阶段只实现 `/tools` 和 `/read`。

### 后续再实现的设计

- 阶段 6 接入 prompt、配置和真实 Qwen/OpenAI-compatible adapter。
- 阶段 7 加入权限和命令执行边界。
- 阶段 8 让 headless/main 保存 session 并支持 replay。
- 阶段 11 扩展 `/session`、`/memory`、`/rewind` 等本地产品命令。

## 常见误区

- 误区 1：headless 是另一个 agent loop。
  - 正确理解：headless 只是运行入口，核心推理和工具循环仍然在 `run_agent_turn`。
- 误区 2：所有 slash command 都应该交给模型理解。
  - 正确理解：确定性的本地命令可以直接分流，这样更稳定、可测试，也更像产品命令。
- 误区 3：CLI 测试只需要测函数，不需要测 `python -m`。
  - 正确理解：函数测试覆盖逻辑，子进程测试覆盖真实入口，二者互补。
- 误区 4：阶段 5 应该顺手接入真实模型。
  - 正确理解：真实模型属于阶段 6。阶段 5 的重点是入口闭环，不是 provider 集成。

## 复习提示

下次复习时，重点理解：
- 为什么 headless 要尽量短，少状态、少交互。
- 为什么 `/tools` 和 `/read` 可以先做成本地命令。
- `main.run` 和 `headless.run_headless` 的职责边界是什么。
- 为什么保留阶段 0 的无参 smoke 行为有助于兼容旧测试。

可以尝试自己回答：
- 如果 `run_headless` 不返回最后一条 assistant 消息，CLI 应该输出什么？
- `/read` 直接执行工具和让 mock model 发起工具调用，各有什么优缺点？
- 为什么阶段 5 不应该保存 session？

## 面试高频问题与参考答案

### 1. CLI 入口和 headless 执行层为什么要分开？

**参考答案：** CLI 负责解析参数、选择标准输出/错误输出和映射退出码；headless 负责执行一次不依赖交互 UI 的 agent turn 并返回结果。分开后，自动化脚本和测试可以直接调用 headless，CLI 只保留进程边界职责。未来增加 TUI 时，也能复用同一个执行核心而不复制 agent 逻辑。

### 2. 什么叫 headless 模式？它适合哪些场景？

**参考答案：** headless 表示不依赖持续交互界面，以输入一条任务、运行一轮、返回最终文本的方式工作。它适合 CI、脚本集成、smoke test 和 API 外层封装，也方便测试注入 cwd 和模型替身。它的限制是无法自然承载多轮确认、实时审批和丰富进度展示，这些需要后续交互产品面。

### 3. 为什么 `/tools`、`/read` 这类本地命令应在调用模型前处理？

**参考答案：** 这些命令语义确定，不需要模型推理，直接处理可以减少延迟、费用和随机性，也能在 provider 未配置时继续使用。分流必须发生在加载真实模型配置之前，否则一个纯本地查询可能因为 API key 缺失而失败。本地命令仍应复用同一工具注册表和 workspace 边界，避免形成旁路。

### 4. CLI 为什么要区分 stdout、stderr 和退出码？

**参考答案：** stdout 用于正常结果，便于管道和脚本消费；stderr 用于错误诊断，避免污染数据输出；退出码让调用方无需解析文本就能判断成功失败。三者形成稳定的进程协议。测试应注入 `StringIO` 分别断言输出，并验证异常不会打印 traceback 或敏感 provider 信息。

### 5. `run_headless()` 为什么只返回最后一条 assistant 内容，而不是整个内部消息列表？

**参考答案：** headless 的产品契约是“一条任务得到一个最终结果”，内部工具调用和协议消息属于 harness 实现细节。提取最后 assistant 文本让 CLI 输出简洁，完整历史仍由 agent loop 返回，后续可以交给 session 层保存。展示结果与保存运行记录是两个不同职责。

### 6. 为什么 cwd、输出流和模型创建函数应设计成可注入边界？

**参考答案：** 可注入边界让测试使用 `tmp_path`、内存流和 scripted model，避免修改真实项目、捕获全局终端或访问网络。它也减少隐藏全局状态，使同一执行函数能被 CLI、测试和未来服务层复用。依赖注入不一定需要复杂框架，显式函数参数通常已经足够。

### 7. 场景题：执行 `/tools` 时程序却提示缺少 API key，你会定位哪里？

**参考答案：** 先检查本地命令分流是否发生在 `load_runtime_config()` 和 `create_model_adapter()` 之前；再确认输入经过 trim 后确实匹配 `/tools`；最后用测试替换配置加载函数为“若被调用就失败”，证明本地命令没有触达 provider 路径。这个故障说明产品控制流顺序错误，而不是配置本身错误。

### 8. 为什么阶段 5 保留“无参数输出 ready”的旧 smoke 行为？

**参考答案：** 这是阶段 0 已建立的安装与入口契约，后续扩展 CLI 不应无理由破坏它。保留兼容行为让最小健康检查仍然快速，也体现增量开发中对已有外部契约的尊重。如果未来要改变，应明确版本和迁移方案，而不是因为内部能力增加就悄悄改变入口。

## 下一阶段衔接

本阶段解决了：

```text
用户可以从命令行把 prompt 送进 MiniCode Lite 的最小 harness，并看到输出。
```

下一阶段要解决：

```text
把 mock-only runtime 升级成可配置 runtime，提前接入真实 Qwen/OpenAI-compatible 模型，同时保留 mock 后备。
```

本阶段产物会这样支撑下一阶段：
- `run_headless` 已经有统一初始化点，后续可替换为 `create_model_adapter`。
- CLI 已经有 prompt 入口，后续可加入配置参数和 provider 诊断。
- `/tools` 和默认工具注册表已经稳定，后续 prompt 构建可以注入工具信息。
