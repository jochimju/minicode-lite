# 阶段 11：本地产品命令学习总结

## 主题

本阶段的主题是：把 session、checkpoint、rewind 和 memory 的内部 Python API，包装成用户可以直接输入的本地 slash 命令。

大白话讲，阶段 8 到阶段 10 已经造好了录像、恢复点和知识卡片，但它们还像藏在机房里的设备，只能由代码调用。阶段 11 增加的是控制面板：用户输入 `/session`、`/rewind-preview` 或 `/memory`，harness 自己完成查询或恢复，不必把这些确定性操作交给模型猜。

## 问题是什么

### 为什么要有这个阶段

如果所有输入都进入模型，就会出现三个问题：查看本地状态也消耗 provider 调用；模型可能把命令理解成自然语言而不是精确操作；危险的 rewind 缺少稳定参数和可测试反馈。内部能力存在不等于产品能力可用，二者之间需要明确的命令路由和展示层。

### 本阶段具体解决的问题

1. 怎样在模型调用前识别本地命令和普通用户任务？
2. one-shot/headless 没有长期存活的 active session，`/session` 应查看什么？
3. 怎样保证显式 session ID 和 active session 都不能跨 workspace 操作？
4. 怎样让 preview 与真正 rewind 共用选择语义，同时保证 preview 零副作用？
5. 怎样让缺少 session、空工具表或尚未创建 memory 时仍返回友好结果？
6. 怎样复用阶段 8 到阶段 10 的核心 API，而不是在命令层重写持久化和恢复逻辑？

## 解决方案

### 最小解决方案

- 新增 `minicode_lite/cli_commands.py`，集中实现命令识别、参数解析、对象选择和文本格式化。
- 支持 `/tools`、`/session`、`/sessions`、`/session-replay`、`/checkpoints`、`/rewind-preview`、`/rewind` 和 `/memory`。
- 保留阶段 5 的 `/read` 快捷命令；`local_commands.py` 改为兼容转发层。
- headless 在读取运行配置、创建 model adapter 之前执行本地命令。
- active session 优先；没有 active session 时，读取当前 workspace 最近保存的 session。
- 显式 session ID、latest session 和 active session 都必须属于当前 workspace。
- rewind 参数只接受 `latest`、正整数 steps 或 checkpoint ID；preview 与执行使用同一解析结果。
- README 增加本地命令速查表和调用示例。

### 为什么这个方案足够

阶段 11 的目标是建立“输入 -> 本地路由 -> 已有内部 API -> 可读输出”的闭环。当前项目还没有持续交互的 REPL/TUI，因此不需要命令补全、历史导航、彩色表格或交互确认界面。命令函数保持普通字符串输入输出，既能直接测试，也能被阶段 15 的交互入口复用。

## 工作原理

### 心智模型

本地命令是 harness 的控制面，agent loop 是模型驱动的数据面。确定性的状态查询和恢复动作走控制面，需要推理的用户任务才走数据面：

```text
用户输入
  -> try_handle_local_command
  -> 已知 slash 命令？
       -> 是：解析 workspace/session/参数
       -> 调用 session、rewind、memory 或 tool registry API
       -> 返回终端文本，不创建模型
  -> 否：load config -> model -> agent loop -> final
```

### 核心对象解释

#### `try_handle_local_command`

它是统一路由入口。返回字符串表示命令已在本地处理，返回 `None` 表示普通任务或未知 slash 输入应继续进入 agent loop。它只负责语法、选择和展示，不复制 session JSON、checkpoint 选择或 memory 加载算法。

#### `_resolve_session`

它统一 active、latest 和显式 session ID 的解析。交互模式未来可以传 active session；现有 headless 则自然回退到当前 workspace 最近一次保存记录。无论来源是什么，都要核对 session 的 workspace，防止从另一个项目查看或恢复文件。

#### `_parse_rewind_target`

它把用户参数变成阶段 9 API 所需的 `steps` 和 `checkpoint_id`。空参数或 `latest` 表示一步，正整数表示回退步数，其他单个字符串按 checkpoint ID 处理，零步和多余参数返回用法提示。

#### `format_session_list`

它消费 `SessionMetadata` 而不是完整 session，从而保持列表命令轻量。每行显示 ID、首条用户消息、消息数和 checkpoint 数，并维持 `list_sessions` 已有的最近更新顺序。

#### `format_memory_status`

它只展示 workspace、memory 文件位置、文件是否存在和条目数。构造 `MemoryManager` 是只读加载；没有 memory 文件时不会为了状态查询创建隐藏目录。

### 当前核心流程

```text
python -m minicode_lite /rewind-preview
  -> main.run
  -> run_headless
  -> try_handle_local_command
  -> 当前 workspace 的 latest session
  -> format_rewind_preview
  -> 展示将恢复的 checkpoint
  -> 文件和 session 均不变化
```

真正执行时只替换最后一步：

```text
/rewind
  -> rewind_session_data
  -> 整批路径预检
  -> 保存反向 checkpoint
  -> 恢复文件
  -> 持久化 session
  -> 返回恢复摘要
```

## 对应核心文档

参考项目路径：`D:\JavaProject\MiniCode-Python-main`

- `minicode/cli_commands.py`
  - 对照统一 slash 命令分流、session 选择和友好空状态。
  - 保留产品命令调用已有核心模块的分层方式，不复制真实项目的大量扩展命令。
- `minicode/main.py` 中 `_handle_local_command`
  - 理解本地命令必须位于模型循环之前，并用 `str | None` 表达是否已处理。
- `README.md` 中 `Everyday Commands`
  - 学习从用户工作流而不是内部类名描述 `/session`、`/memory` 和 `/rewind-preview`。

## 学习产出

### 新增和修改代码

- `minicode_lite/cli_commands.py`：阶段 11 的统一命令路由、参数解析和格式化。
- `minicode_lite/local_commands.py`：保留旧导入路径的兼容转发层。
- `minicode_lite/headless.py`：改用统一命令模块，并继续在 provider 配置前分流。
- `README.md`：增加 8 个本地产品命令的速查说明。

### 新增和修改测试

- `tests/test_cli_commands.py`：直接覆盖每个命令、workspace 隔离、参数错误、无 session、preview 零副作用和 rewind 恢复。
- `tests/test_headless.py`：验证 `/memory` 不加载 runtime config，证明本地命令真正绕过模型路径。

### 本阶段最终能力

- 用户可离线列工具、查看会话、列历史、回放 transcript 和查看 checkpoint。
- 用户可先预览再执行 rewind，执行后仍保留反向恢复点。
- 用户可查看当前项目 memory 的存储状态与条目数。
- headless 能稳定区分已知本地命令和需要模型处理的普通任务。
- session 相关命令不能跨 workspace 读取或恢复。

## 测试验证

收尾验证命令：

```powershell
python -m pytest -q
python -m compileall -q minicode_lite
git diff --check
python -m minicode_lite /memory
python -m minicode_lite /sessions
```

2026-07-20 的全量结果：

```text
134 passed, 1 skipped
```

跳过项仍是需要显式开关和真实配置的 live Qwen 测试。重点验证了 8 个阶段命令、空状态提示、active/latest/显式 ID 选择、workspace 隔离、无 provider 的本地执行、preview 零副作用、rewind 文件恢复和反向 checkpoint。

## 和真实 MiniCode-Python 的差异

### 保留的设计

- 本地命令在模型和 agent loop 之前分流。
- session、replay、checkpoint、rewind 和 memory 由统一产品入口暴露。
- 命令层调用已有领域 API，不自己读写 session JSON。
- 无 active session 和无 checkpoint 都返回可读提示。

### 简化的设计

- 当前没有常驻 TTY/TUI，active session 只作为可选注入参数，headless 默认读取 latest。
- 输出是稳定纯文本，没有富文本、表格渲染、命令补全和分页。
- rewind 只操作当前 workspace 最近 session；没有真实项目的 `/session-rewind <id>` 扩展语法。
- `/memory` 只展示 project memory 文件和条目数，不展示多层作用域、检索统计或优化状态。
- 未知 slash 输入仍交给模型，尚未提供 `/help` 命令清单。

### 后续再实现的设计

- 阶段 12 增加 `/readiness` 和运行日志，让控制面能解释“为什么当前不能工作”。
- 阶段 15 的 REPL/TUI 将传入真正的 active session，并复用本命令路由。
- 只有出现真实交互需求后再增加确认对话、补全、历史和富文本展示。

## 常见误区

- 误区：slash 命令只是给模型看的特殊 prompt。
  - 本地产品命令由 harness 确定性执行，不应依赖模型是否正确理解，也不应产生 provider 成本。
- 误区：headless 没有 active session，所以 `/session` 没有意义。
  - one-shot 模式完成普通任务后已经保存 session；下一次独立调用可读取当前 workspace 的 latest session。
- 误区：校验显式 session ID 就足够安全。
  - ID 合法只防目录穿越，还必须校验加载出的 session.workspace，才能阻止跨项目查看和 rewind。
- 误区：`/rewind-preview` 可以先调用 rewind 再把文件改回去。
  - 那会产生磁盘和 session 副作用，也可能在中途失败；preview 必须只选择并格式化 checkpoint。
- 误区：命令层应该直接解析 session JSON，减少函数调用。
  - 这会复制 schema 和安全规则。命令层应复用 `list_sessions`、`format_session_replay` 和 `rewind_session_data` 等权威 API。

## 复习提示

重点理解：为什么本地命令在配置加载之前；为什么返回 `None` 是路由协议；为什么 active 和 saved session 都要做 workspace 校验；为什么 preview 与 rewind 共享参数但不能共享副作用。

自测问题：

1. `/memory` 为什么在没有 API key 时仍能工作？
2. headless 第二次启动后，`/session` 怎样找到上一次任务？
3. active session 为什么不能无条件优先？
4. `/rewind-preview 2` 与 `/rewind checkpoint-id` 最终怎样映射到阶段 9 API？
5. 为什么未知 slash 命令返回 `None`，而已知命令的错误参数返回 Usage？

## 面试高频问题与参考答案

### 1. 本地产品命令在 agent harness 中解决什么问题？

**参考答案：** 它为确定性的运行时状态和控制动作提供不经过模型的入口。用户查看 session、memory 或执行 rewind 时，需要稳定语义、低延迟和可测试结果；如果交给模型，不但浪费 provider 调用，还可能产生理解偏差。命令层因此位于输入入口和 agent loop 之间。

### 2. `try_handle_local_command` 为什么返回 `str | None`？

**参考答案：** 字符串表示输入已由本地控制面消费，调用方应直接展示结果；`None` 表示本地命令层不拥有该输入，调用方应继续进入模型路径。这个返回协议让路由与 CLI 输出解耦，也方便 headless 和未来 REPL 复用同一函数。

### 3. `/session` 在 active session 和 latest saved session 之间如何选择？

**参考答案：** 当前调用方传入且属于同一 workspace 的 active session 优先，因为它可能比磁盘更新；没有合格 active session 时，按 workspace 过滤并选择最近更新的持久化 session。显式 ID 同样必须通过 workspace 校验，不能只验证 ID 格式。

### 4. 取舍题：为什么不直接复制真实 MiniCode-Python 的全部 slash 命令？

**参考答案：** 阶段目标是暴露已经实现的 session、checkpoint 和 memory 能力。真实项目还有 readiness、扩展、MCP、模型管理和复杂产品状态，如果现在全部复制，只会制造没有底层能力支撑的空命令。最小命令集合足以验证控制面边界，其余能力应随对应阶段加入。

### 5. `/rewind-preview` 的安全边界是什么？

**参考答案：** 它只调用 checkpoint 选择和文本格式化，不读取、写入或删除目标文件，也不修改 session.checkpoints。真正 `/rewind` 才会进入阶段 9 的整批路径预检、反向快照和恢复逻辑。测试必须同时断言文件内容与 checkpoint ID 列表保持不变。

### 6. 怎样测试本地命令确实没有偷偷调用模型？

**参考答案：** 在 headless 测试中把 `load_runtime_config` 或 `create_model_adapter` 替换成一旦调用就失败的函数，再执行 `/tools` 或 `/memory`。命令仍成功返回，才能证明分流发生在配置和模型创建之前；只测试格式化函数不足以覆盖真实入口顺序。

### 7. 场景题：在项目 A 执行 `/session abc123`，但该 ID 属于项目 B，应怎样处理和排查？

**参考答案：** 命令应返回当前 workspace 没有可用 session，不能展示项目 B 内容。排查时先验证 ID 格式和是否能加载，再比较 `Path(session.workspace).resolve()` 与当前 cwd；最后检查 active session 分支是否也执行相同校验，避免只保护磁盘加载路径。

### 8. 命令层为什么不直接打开 session JSON 和 memory JSON？

**参考答案：** JSON schema、损坏降级、路径验证和恢复顺序都属于领域模块的职责。命令层直接读写会形成第二套规则，后续 schema 变化时容易漂移，并可能绕过阶段 9 的安全预检。正确分工是命令层解析用户意图，领域 API 管理状态和副作用。

### 9. 已知命令参数错误与未知 slash 命令为什么处理不同？

**参考答案：** 已知命令属于本地控制面的命名空间，参数错误应立即返回稳定 Usage，不能交给模型猜；未知 slash 输入当前仍可能是用户希望模型解释的文本，所以返回 `None`。未来若产品决定所有 slash 名称都保留，可以再改成统一 unknown-command 提示。

### 10. 当前实现与真实 MiniCode-Python 的主要差异是什么？

**参考答案：** 轻量版保留了前置分流、统一命令入口、session/replay/rewind/memory 产品面和友好空状态，但只提供纯文本 one-shot 体验。真实项目有常驻交互 session、更丰富命令、readiness、扩展面和详细运行时状态；这些将在后续阶段按底层能力逐步加入。

## 下一阶段衔接

本阶段解决了：

```text
用户可以直接查看和控制已有 session、checkpoint、rewind 与 memory 能力。
```

阶段 12 要解决：

```text
控制面虽然可操作，但还不能系统回答运行时是否 ready、provider 为什么不可用、工具和 turn 如何留下诊断日志。
```

`try_handle_local_command` 已形成统一扩展点，阶段 12 可以增加 `/readiness`；现有“本地命令先于模型”的测试方式也能直接验证 readiness 在 provider 缺失时仍给出诊断。
