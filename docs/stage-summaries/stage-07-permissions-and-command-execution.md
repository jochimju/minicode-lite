# 阶段 07：权限管理和命令执行学习总结

## 主题

本阶段的主题是：在“模型能够提出动作”和“本机真的执行动作”之间加入权限闸门，并实现一个受路径、审批、超时和输出大小约束的 `run_command` 工具。

大白话讲，前几个阶段让 agent 长出了读写文件和调用真实模型的能力，但“模型建议执行”不等于“用户已经同意执行”。阶段 7 增加一名守门员：查看工作区内文件可以直接进行，走出工作区、修改文件或执行非只读命令时，必须先拿到明确授权；没有人可以确认时就拒绝。

## 问题是什么

### 为什么要有这个阶段

真实模型输出是不可信输入。即使模型本意正确，它也可能生成错误路径、覆盖重要文件、运行具有副作用的命令，或把下载内容直接交给 shell 执行。如果工具看到调用就立即产生副作用，那么 workspace 只是路径工具的局部约束，不能形成完整的运行时安全边界。

本阶段要解决三个不同问题：

1. 路径能否访问：规范化后的目标是否仍在当前工作区内？
2. 修改是否获批：用户是否看过这次具体变化并允许写盘？
3. 命令能否执行：它是保守的只读命令，还是需要审批的写入、解释器或 shell 片段？

这三类检查不能混为一个布尔开关。路径在 cwd 内，只表示位置合法，不表示覆盖内容已经获得同意；命令在 cwd 内运行，也不表示它不会删除文件或访问外部系统。

## 解决方案

### 最小解决方案

- 新增 `PermissionManager`，集中处理路径、编辑和命令审批。
- prompt handler 使用结构化请求，并可由测试注入；无 handler 时高风险操作默认拒绝。
- 路径先通过 `resolve(strict=False)` 规范化，再按完整路径段判断是否位于 workspace 内。
- 文件工具先计算最终内容和 unified diff，审批通过后才调用写盘函数。
- `run_command` 只让保守只读集合免审批，其他命令、解释器和 shell 控制符都进入审批。
- 普通命令使用 argv 和 `shell=False` 执行；只有已审批的复合 shell 片段才显式启动 shell。
- 命令设置 1–300 秒超时范围，并把输出限制在 20,000 字符内。
- agent loop 在 turn 开始时初始化临时授权，并在正常返回或异常时统一撤销。

### 为什么这个方案足够

当前目标不是复制真实 MiniCode 的持久权限库、auto mode 或完整 TTY 审批界面，而是先证明安全顺序成立：

```text
不可信输入
  -> 规范化与分类
  -> 权限决策
  -> 执行副作用
  -> 结构化结果
```

只要拒绝发生在副作用之前、无交互时默认拒绝、测试能够观察审批请求，就已经形成可验证的最小权限 harness。持久化授权和更丰富的产品界面可以在这个边界上继续扩展。

## 工作原理

### 心智模型

可以把阶段 7 看成三道依次收紧的门：

```text
模型 ToolCall
  -> 路径门：动作发生在哪里？
  -> 意图门：是读取、编辑还是执行命令？
  -> 风险门：能自动放行，还是必须让用户决定？
  -> 文件系统 / 子进程
  -> ToolResult
```

`ToolRegistry` 仍负责输入校验和异常隔离，`PermissionManager` 只负责“是否允许”，具体工具只在获准后执行。这种分工让权限策略不会渗进 provider adapter，也不会让 agent loop 理解每一种命令。

### 核心对象解释

#### `PermissionManager`

它保存规范化的 workspace 根、可选 prompt handler 和本轮临时授权。核心方法是：

- `ensure_path_access()`：cwd 内直接允许；cwd 外请求审批。
- `ensure_edit()`：先复查路径，再携带 diff 请求编辑审批。
- `ensure_command()`：携带 cwd、完整命令签名和风险原因请求审批。
- `begin_turn()` / `end_turn()`：建立并撤销 `allow_turn`、`allow_all_turn` 状态。
- `get_summary()`：提供不含 handler 和内部状态的 prompt 摘要。

审批决策只接受 `allow_once`、`allow_turn`、`allow_all_turn` 和 `deny_once`。未知返回值按拒绝处理，避免 UI bug 变成隐式授权。

#### 路径规范化

权限比较使用解析后的绝对路径，而不是模型传入的表面字符串。这样 `..`、相对路径和符号链接会先被折叠。Windows 上使用 `normcase`，以符合常见文件系统大小写不敏感的语义；`commonpath` 按路径段比较，避免把 `repo-other` 误认为 `repo` 子目录。

#### 编辑审批

`write_file`、`edit_file` 和 `patch_file` 都遵循同一顺序：

```text
解析目标路径
  -> 读取旧内容
  -> 在内存中计算新内容
  -> 生成有上限的 unified diff
  -> ensure_edit
  -> 写盘
```

因此替换找不到、补丁中途失败或审批拒绝时，磁盘内容不会改变。`patch_file` 仍保持“全部替换成功后只写一次”的原子性边界。

#### `run_command_tool`

命令工具把输入规范为 `command + args`，解析可选 cwd 和 timeout，然后进行风险分类：

- `echo`、`pwd`、`ls`、`rg` 等保守查看命令默认放行。
- `git status/diff/log/show` 作为明确的只读子命令放行。
- 解释器、删除命令、危险 git 命令和未知命令需要审批。
- 管道、连接符、重定向、下载后执行，以及 Windows shell 展开符需要审批。

审批通过后，普通命令仍以 `shell=False` 和 argv 执行。命令退出码为 0 时 `ToolResult.ok=True`；非零退出码、超时、命令不存在和权限拒绝都返回可供模型读取的失败结果。

#### agent loop 权限生命周期

`run_agent_turn()` 在进入实际循环前调用 `begin_turn()`，并通过 `try/finally` 调用 `end_turn()`。这样 `allow_turn` 只影响当前模型工具循环，即使 `model.next()` 抛错也不会泄漏到下一轮。

### 当前核心流程

文件修改流程：

```text
ToolCall(write/edit/patch)
  -> resolve_tool_path
  -> PermissionManager.ensure_path_access
  -> 内存中生成最终内容和 diff
  -> PermissionManager.ensure_edit
  -> write_text_file
  -> ToolResult
```

命令执行流程：

```text
ToolCall(run_command)
  -> validator
  -> 解析 cwd 和 argv
  -> 只读/危险/shell 分类
  -> 必要时 PermissionManager.ensure_command
  -> subprocess.run(shell=False)
  -> 超时处理 + stdout/stderr 合并 + 截断
  -> ToolResult
```

## 对应核心文档

参考项目路径：`D:\JavaProject\MiniCode-Python-main`

- `minicode/permissions.py`
  - 对照了路径规范化、Windows 大小写处理、命令风险分类、编辑审批和 turn 级授权。
- `minicode/workspace.py`
  - 对照了工具路径统一解析和权限策略接管边界。
- `minicode/tools/run_command.py`
  - 对照了只读命令、Windows shell builtin、危险 shell 片段、超时和输出截断。
- `minicode/tools/write_file.py`、`edit_file.py`、`patch_file.py`
  - 对照了“计算预览、审批、再写盘”的顺序。
- `tests/test_permissions.py`、`tests/test_tools.py`
  - 对照了注入 prompt handler、拒绝时不执行和跨平台命令测试方法。

## 学习产出

### 新增代码

- `minicode_lite/permissions.py`：最小权限管理器、路径比较、命令和 shell 风险分类。
- `minicode_lite/tools/run_command.py`：受审批保护的前台命令工具。

### 扩展代码

- 三个写工具增加 diff 预览和编辑审批。
- 默认工具注册表加入 `run_command`。
- agent loop 增加 turn 级权限生命周期。
- headless 创建默认拒绝高风险行为的权限管理器。
- local command 的 `/read` 复用同一个权限上下文。
- system prompt 注入实际权限摘要。

### 新增测试

- `tests/test_permissions.py` 覆盖 cwd 内读、cwd 外写拒绝、外部路径批准、turn 编辑授权和危险命令分类。
- `tests/test_tools.py` 覆盖编辑拒绝不落盘、批准后写盘、只读 echo、危险命令和下载执行片段在进程启动前被拦截、超时和输出截断。
- `tests/test_agent_loop.py` 覆盖模型异常时仍关闭权限生命周期。
- `tests/test_prompt.py` 覆盖权限摘要注入。

## 测试验证

本阶段收尾执行：

```powershell
python -m pytest -q
python -m compileall -q minicode_lite
git diff --check
```

2026-07-17 的全量测试结果为：

```text
88 passed, 1 skipped
```

跳过项仍是需要显式开关和真实配置的 live Qwen 测试。阶段 7 的命令测试不联网，危险命令和下载执行载荷都通过 monkeypatch 证明在审批拒绝后没有启动进程。

## 和真实 MiniCode-Python 的差异

### 保留的设计

- 路径先规范化，再进行工作区包含关系判断。
- 权限通过 `ToolContext` 注入，文件和命令工具不依赖全局单例。
- 读取、编辑和命令采用不同审批请求。
- 普通命令尽量不用 shell；危险 shell 片段在执行前审批。
- 编辑支持 turn 级授权，并在 turn 结束后撤销。

### 简化的设计

- 只有四种瞬时决策，没有 `allow_always`、`deny_always` 和权限文件持久化。
- 没有 auto mode、风险评分或完整命令 allowlist 配置。
- 没有后台命令、PTY、流式输出和进程任务管理。
- headless 没有交互审批 UI，所以高风险行为默认拒绝。
- diff 预览采用统一的字符上限，没有语法感知或大文件分页。

### 后续再实现的设计

- 持久权限、审批审计和更完整的 TTY/TUI prompt handler。
- 更细的命令段解析、平台专用安全规则和进程树终止。
- checkpoint 接入后，在编辑审批通过与写盘之间创建恢复点。
- session 接入后，保存权限结果和工具执行记录用于 replay。

## 常见误区

- 误区 1：路径在 cwd 内就可以直接修改。
  - 正确理解：路径合法与用户同意修改是两件事，所以 `ensure_path_access` 后还要 `ensure_edit`。
- 误区 2：没有配置权限管理器等于全部允许。
  - 正确理解：文件工具仍有 workspace 默认边界；命令工具对非只读行为采用 fail closed。
- 误区 3：只检查命令第一个单词就足够。
  - 正确理解：`echo ok | sh` 的第一个单词无害，但 shell 控制符改变了整体语义，必须检查完整命令行。
- 误区 4：把命令放进 cwd 就不会影响外部世界。
  - 正确理解：解释器、网络客户端、git push 和磁盘命令的影响范围不由 cwd 决定。
- 误区 5：审批完成后可以保留到下次 turn。
  - 正确理解：`allow_turn` 必须在正常结束和异常路径上都撤销，否则临时授权会变成长久后门。
- 误区 6：超时只要返回错误文本即可。
  - 正确理解：底层执行器还必须终止超时进程；本阶段使用 `subprocess.run(timeout=...)` 让标准库负责终止直接子进程。

## 复习提示

下次复习时，重点重新回答：

- 为什么路径审批和编辑审批要分开？
- 为什么 diff 必须在写盘前生成？
- 为什么普通命令使用 argv + `shell=False` 更安全？
- `allow_once`、`allow_turn` 和 `allow_all_turn` 的状态范围分别是什么？
- 为什么 Windows 的 `%`、`!`、`^` 也属于命令风险信号？
- 为什么输出截断要同时保留头部和尾部？

自测问题：

1. 模型请求写入 `../shared/config.py` 时，会依次触发哪些检查？
2. `git status` 和 `git reset --hard` 为什么不能采用相同默认策略？
3. 如果 prompt handler 返回拼错的 `allow_onse`，当前实现会怎样处理？
4. 同一 turn 对一个文件选择 `allow_turn` 后，第二次编辑为什么不再 prompt？
5. 模型在本轮抛异常后，为什么下一轮不会继承编辑授权？

## 下一阶段衔接

本阶段解决了：

```text
模型提出本地副作用时，先经过可测试、默认拒绝高风险行为的权限边界。
```

阶段 8 要解决：

```text
一次 turn 的消息、工具调用和结果仍只存在内存中，程序退出后无法检查和回放。
```

本阶段产物会这样支撑下一阶段：

- `ToolResult` 已包含权限拒绝、命令输出和超时信息，可直接写入 session transcript。
- 权限生命周期已经与 agent turn 对齐，session 可以按 turn 保存审批后的实际执行记录。
- 路径和命令都已规范化，后续 replay 能保存稳定、可解释的运行信息。
