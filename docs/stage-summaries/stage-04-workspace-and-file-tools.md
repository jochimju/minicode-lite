# 阶段 04：工作区边界和文件工具 学习总结

## 主题

本阶段的主题是：让 MiniCode Lite 具备安全读写当前项目文件的最小能力。

大白话讲：

- 前三阶段已经让 agent 能“想”和“调用工具”，但它还不能真正碰项目文件。
- 阶段 4 给 agent 装上最基础的“手”，同时给这只手加上护栏：默认只能操作当前工作区内的路径。

## 问题是什么

### 为什么要有这个阶段

如果没有文件工具，agent loop 只能调用测试里的假工具，无法读取代码、写入文件、做小范围修改。真正的 coding harness 一定要能把模型意图落到本地文件系统上。

但文件系统也是风险边界。如果工具随便接受 `../outside.txt` 或绝对路径，agent 可能读写项目外的文件。因此这一阶段先建立一个统一路径入口，再让所有文件工具复用它。

### 本阶段具体要解决的问题

1. 如何把模型传入的相对路径解析成工作区内的真实路径。
2. 如何拒绝默认越界路径，避免工具读写当前项目之外的文件。
3. 如何实现最小文件工具：列目录、读文件、写文件、单段替换、多段替换。

## 解决方案

### 最小解决方案

本阶段采用的最小实现方案：

- 新增 `minicode_lite/workspace.py`，用 `resolve_tool_path(context, path, mode)` 统一解析工具路径。
- 新增 `minicode_lite/tools/`，每个文件工具独立成小模块。
- 新增 `create_default_tool_registry()`，把阶段 4 的文件工具注册到 `ToolRegistry`。
- 新增 `tests/test_workspace.py` 和 `tests/test_tools.py`，使用 `tmp_path` 验证所有文件行为。

### 为什么这个方案足够

这一阶段只负责“能安全读写项目文件”。真实 MiniCode-Python 里的权限审批、写前 review、checkpoint、rewind、命令执行都很重要，但它们会让学习路径变复杂，所以按阶段计划后置。

## 工作原理

### 你要建立的心智模型

文件工具不是直接操作字符串路径，而是先经过工作区边界检查。可以把 `resolve_tool_path` 理解成文件工具的门卫：

- 工具说：“我要读 `demo.txt`。”
- 门卫把它变成真实路径。
- 门卫确认它还在当前项目里。
- 通过后，具体工具才读写文件。

### 核心对象解释

#### `ToolContext`

`ToolContext` 保存工具运行时上下文。阶段 4 主要使用 `cwd`，也预留了 `permissions`、`session`、`runtime` 给后续阶段。

#### `resolve_tool_path`

它负责把工具输入路径解析为 `Path`。没有权限管理器时，它默认只允许访问 `context.cwd` 内的路径；有权限管理器时，则把路径和意图交给 `permissions.ensure_path_access()`。

#### `read_file_tool`

读取 UTF-8 文本文件。遇到二进制文件、目录、缺失文件时返回 `ToolResult(ok=False)`，而不是让异常冲垮 agent loop。

#### `write_file_tool`

写入 UTF-8 文本文件，并自动创建父目录。这是最小写入能力，后续 checkpoint 阶段会在写入前记录快照。

#### `edit_file_tool`

做单段精确替换。默认要求匹配唯一；如果同一段文本出现多次，会提示使用 `replace_all=true` 或提供更具体上下文。

#### `patch_file_tool`

在同一个文件里按顺序应用多段精确替换。它适合一次性修改多个位置，但仍然保持简单：没有实现完整 unified diff parser。

#### `list_files_tool`

列出目录下的文件和子目录，输出 `dir name` 或 `file name`。它帮助后续 CLI/headless 先观察项目结构。

### 当前核心流程

```text
model tool call
  -> ToolRegistry.execute
  -> file tool validator
  -> resolve_tool_path
  -> read/write/edit/list disk
  -> ToolResult
  -> agent loop appends tool_result
```

## 对应核心文档

参考项目路径：

- `D:\JavaProject\MiniCode-Python-main`

本阶段对应的真实 MiniCode-Python 模块和理解重点：

- `minicode/workspace.py`
  - 工具路径统一解析。
  - 没有权限管理器时默认阻止越界路径。
- `minicode/tools/read_file.py`
  - UTF-8 文本读取。
  - 二进制文件返回友好错误。
- `minicode/tools/write_file.py`
  - 写入工具只负责输入校验和交给文件变更流程。
- `minicode/tools/edit_file.py`
  - 精确字符串替换和多匹配保护。
- `minicode/tools/patch_file.py`
  - 多段替换在一个工具调用里完成。
- `minicode/tools/list_files.py`
  - 目录列表是 agent 观察工作区的基础工具。
- `tests/test_tools.py`
  - 使用 `tmp_path` 隔离文件系统测试。

## 学习产出

### 新增代码

- `minicode_lite/workspace.py`
  - 提供统一路径解析和工作区边界检查。
- `minicode_lite/tools/__init__.py`
  - 暴露阶段 4 默认文件工具注册表。
- `minicode_lite/tools/_shared.py`
  - 放置文件工具共用的路径、读写辅助函数。
- `minicode_lite/tools/list_files.py`
  - 实现目录和文件列表工具。
- `minicode_lite/tools/read_file.py`
  - 实现 UTF-8 文本读取工具。
- `minicode_lite/tools/write_file.py`
  - 实现 UTF-8 文本写入工具。
- `minicode_lite/tools/edit_file.py`
  - 实现单文件精确替换工具。
- `minicode_lite/tools/patch_file.py`
  - 实现多段精确替换工具。

### 新增测试

- `tests/test_workspace.py`
  - 验证工作区内路径允许、越界路径拒绝、权限管理器委托。
- `tests/test_tools.py`
  - 验证读、写、编辑、patch、列目录、越界拒绝、默认工具注册。

### 新增文档

- `docs/stage-summaries/stage-04-workspace-and-file-tools.md`
  - 用于后续复习阶段 4 的设计边界和学习重点。

### 本阶段最终能力

完成后，项目已经具备：

- agent 可通过工具读取当前工作区内的文本文件。
- agent 可写入新文件并创建父目录。
- agent 可对已有文件做精确替换和多段替换。
- 所有文件工具默认拒绝访问工作区外路径。

## 测试验证

执行的验证命令：

```powershell
python -m pytest -q
```

验证结果：

- `33 passed`

重点验证行为：

- `../outside.txt` 这种越界路径会被拒绝。
- 二进制文件读取返回友好错误。
- `write_file`、`edit_file`、`patch_file` 会真实修改 `tmp_path` 中的文件。
- 默认工具注册表包含阶段 4 的五个文件工具。

## 和真实 MiniCode-Python 的差异

### 保留的设计

- 保留统一路径解析入口。
- 保留工具输入校验和结构化 `ToolResult`。
- 保留精确替换、多匹配保护、二进制读取错误。

### 简化的设计

- `read_file` 暂不实现 offset/limit 和读取缓存。
- `edit_file` 暂不实现模糊空白匹配和详细 diff 诊断。
- `patch_file` 只实现多段字符串替换，不解析完整 patch 格式。
- `list_files` 不做隐藏文件过滤、深度限制或文件树输出。

### 后续再实现的设计

- 阶段 7 再实现权限审批和更完整的路径/命令边界。
- 阶段 9 再实现写前 checkpoint 和 rewind。
- 阶段 11 再把这些能力包装成本地产品命令。

## 常见误区

- 误区 1：文件工具自己检查路径就行。
  - 正确理解：路径边界应该集中在 `resolve_tool_path`，否则每个工具都会长出一套不一致的安全逻辑。
- 误区 2：`edit_file` 和 `patch_file` 是同一个东西。
  - 正确理解：`edit_file` 适合一次精确替换，`patch_file` 适合一个文件中的多段替换。
- 误区 3：测试里直接读写当前项目文件。
  - 正确理解：文件工具测试应该用 `tmp_path`，让测试可重复、可隔离、不会污染真实项目。

## 复习提示

下次复习时，重点理解：

- 为什么所有文件工具都必须先经过 `resolve_tool_path`。
- 为什么工具错误要变成 `ToolResult(ok=False)`。
- 为什么阶段 4 不急着实现权限审批和 checkpoint。

可以尝试自己回答：

- 如果没有 `resolve_tool_path`，哪个工具最容易绕过工作区边界？
- 为什么二进制文件不能直接按文本塞进 tool result？
- `edit_file` 发现多个匹配时为什么不默认全部替换？

## 面试高频问题与参考答案

### 1. workspace boundary 在 coding agent 中解决什么问题？

**参考答案：** 它把模型可操作的文件范围限制在当前项目根目录内，避免相对路径、绝对路径或符号链接让工具访问任意本机文件。工具是 agent 的“手”，workspace boundary 是这只手的默认活动范围。它不能替代所有权限审批，但提供了没有高级权限系统时仍然有效的最小安全边界。

### 2. 为什么路径检查必须在 `resolve()` 之后进行？

**参考答案：** 表面字符串可能包含 `.`、`..` 或经过符号链接指向工作区外。如果先用字符串前缀判断，`workspace/../secret` 可能看似以 workspace 开头却实际逃逸。先把 cwd 和目标规范成真实绝对路径，再按路径段判断包含关系，才能让比较对应最终访问位置。

### 3. 为什么所有文件工具都应复用同一个 `resolve_tool_path()`？

**参考答案：** 路径边界属于横切安全规则，分散实现会产生不一致：read 可能阻止逃逸，而 patch 忘了检查。统一入口保证 list、read、write、edit 和 patch 采用同样的相对路径解释、规范化和权限扩展点。后续加入 `PermissionManager` 时也只需让统一入口委托策略，而不是重写每个工具。

### 4. 为什么文件工具明确使用 UTF-8，并额外检测二进制内容？

**参考答案：** 明确 UTF-8 可以避免不同操作系统默认编码导致同一文件行为不一致。仅捕获解码错误还不够，因为某些二进制数据可能碰巧能解码，所以 NUL 字符可作为保守补充信号。coding agent 的文本工具不应把乱码或巨大二进制内容送进模型上下文，二进制处理应交给专用工具。

### 5. `edit_file` 为什么默认要求旧文本唯一匹配？

**参考答案：** 精确且唯一的匹配让模型的修改意图与实际落点一一对应。如果同一文本出现多次而默认全部替换，可能意外修改无关逻辑；如果悄悄只改第一处，也可能选错位置。遇到多处匹配时返回错误，要求调用方提供更具体上下文或显式 `replace_all`，是用可恢复失败换取编辑确定性。

### 6. `patch_file` 如何避免“只应用了一半”的文件状态？

**参考答案：** 它先在内存字符串上按顺序验证和应用全部 replacement，任一段找不到就返回失败，不写磁盘；只有全部成功后才进行一次写回。这不是跨进程意义上的完整事务，也还没有 checkpoint，但已经避免了工具自身在中途失败时留下半成品。

### 7. 场景题：`../outside.txt` 被拒绝了，但攻击者在工作区内创建一个指向外部目录的符号链接，系统应如何防守？

**参考答案：** 路径解析必须跟随符号链接得到规范化目标，然后再与 workspace 根比较，而不能只检查输入中的相对路径。测试应创建真实外部目标和链接，断言解析后被拒绝。还要认识到检查与实际打开之间可能存在 TOCTOU 风险，生产级实现可能需要更强的文件描述符或平台级隔离；阶段 4 先建立解析后的边界。

### 8. 为什么阶段 4 没有同时实现审批、checkpoint 和任意文件格式工具？

**参考答案：** 本阶段只回答“如何让 agent 在当前项目内可靠读写文本文件”。审批属于动作授权，checkpoint 属于恢复机制，二进制和结构化格式又有各自解析复杂度。把它们分阶段实现，能分别测试 workspace、permission 和 recovery 的职责，避免一个失败同时跨越多层而难以定位。

## 下一阶段衔接

本阶段解决了：

```text
agent 可以安全地读写当前项目文件
```

下一阶段要解决：

```text
从命令行跑单轮任务，并把 mock model、agent loop、文件工具串起来
```

本阶段产物会这样支撑下一阶段：

- `create_default_tool_registry()` 可以直接被 headless/CLI 初始化使用。
- `/read <path>` 可以通过 mock model 调用 `read_file`，形成命令行最小闭环。
