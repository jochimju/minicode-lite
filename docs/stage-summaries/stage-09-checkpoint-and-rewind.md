# 阶段 09：checkpoint 和 rewind 学习总结

## 主题

本阶段的主题是：让文件修改从“写错只能自己补救”升级为“每次写前自动留底，出错后可预览并恢复”。

大白话讲，session 已经像行车记录仪一样保存 agent 做过什么，但记录事故不等于修复事故。checkpoint 是文件写入前的照片，rewind 则按照片把磁盘恢复到旧状态。它们共同让 harness 具备恢复优先的基本能力。

## 问题是什么

没有 checkpoint 时，`write_file`、`edit_file` 和 `patch_file` 一旦成功写盘，session 虽能回放工具调用，却没有恢复文件所需的旧内容。阶段 9 具体解决：

1. 快照应在权限审批、参数校验和路径校验之后，还是之前创建？
2. 新文件与已有文件需要怎样不同的恢复语义？
3. 连续修改怎样按步回退，并确保同一文件恢复到最早选中状态？
4. preview 怎样只说明影响范围而保持零副作用？
5. 持久化路径被篡改或磁盘对象变化时，怎样守住 workspace 与批量恢复边界？

## 解决方案

### 最小解决方案

- 在 `SessionData` 中增加 `FileCheckpoint` 列表，并把数量同步到 metadata。
- checkpoint 保存绝对文件路径、原文件是否存在、旧内容、类型和恢复组 ID。
- 三种写工具共用 `checkpoint_for_tool`，固定执行顺序为：路径与内容校验 -> diff 审批 -> 持久化 checkpoint -> 写盘。
- `steps` 选择末尾若干恢复点；`checkpoint_id` 选择目标点到最新的全部恢复点。
- rewind 倒序应用快照，使多次编辑同一文件能回到最早选中的状态。
- rewind 前先捕获当前文件状态，生成 `kind="rewind"` 的反向安全快照，让回退动作本身可撤销。
- preview 与 checkpoint 列表只读取 session 内存，不读取或修改目标文件。
- 恢复前整批校验所有路径仍在 session workspace 内，且当前目标只能是普通文件或不存在。

### 为什么这个方案足够

阶段目标是证明 `write -> snapshot -> restore` 闭环，不是建立版本控制系统。全量文本快照便于理解、检查和测试；真实项目的 delta、压缩、容量清理、并发锁与冲突合并继续后置。

## 工作原理

### 心智模型

checkpoint 不是“修改后的版本”，而是“这次修改发生前，怎样回去”的撤销指令：

```text
文件工具准备新内容
  -> workspace 路径检查
  -> permission diff 审批
  -> FileCheckpoint（旧状态）持久化
  -> 写入新内容
  -> session 保存可恢复历史
```

rewind 是一笔新的有副作用操作，因此也要先为自己留退路：

```text
选择恢复点
  -> 整批路径/对象预检
  -> 捕获当前磁盘状态为 rewind 安全组
  -> 倒序应用旧快照
  -> 用安全组替换已消费的恢复点
  -> 保存 session
```

### 核心对象解释

#### `FileCheckpoint`

它描述一个文件在某次写入前的状态。`existed=True` 表示 rewind 应写回 `previous_content`；`existed=False` 表示该次写入创建了新文件，rewind 应删除它。`kind` 区分普通编辑快照和反向恢复快照，`group_id` 保证一次多文件 rewind 的安全快照不可被拆开。

#### `create_file_checkpoint`

它接收已经过 workspace 解析的目标，生成 ID 并立即保存 session。先保存快照再写文件是关键安全顺序：如果 session 落盘失败，原文件还没有被覆盖。

#### `_select_checkpoints_to_rewind`

它只决定要消费哪些快照，不操作磁盘。`steps=2` 选择最后两个普通编辑；指定 ID 时，从该快照一直恢复到最新。若末尾是同一 rewind group，则整组都被选中，避免只撤销一部分文件。

#### `rewind_session_data` 与 `rewind_session`

前者操作已经加载的 session，后者按 ID 加载后复用前者。恢复前先验证整批目标，再捕获当前状态；恢复时从新到旧倒序应用，最后将旧 checkpoint 替换为反向安全 checkpoint 并持久化。

#### `format_rewind_preview` 与 `format_session_checkpoints`

两者属于只读展示层。preview 复用选择逻辑，保证“预告会恢复什么”和真实执行选择一致；checkpoint 列表展示当前仍可使用的恢复点与类型。

## 对应核心文档

参考项目路径：`D:\JavaProject\MiniCode-Python-main`

- `minicode/session.py`
  - 对照 `FileCheckpoint`、`create_file_checkpoint`、选择逻辑、反向安全快照、preview 和格式化。
- `minicode/file_review.py`
  - 对照“diff 审批通过后、写盘前创建 checkpoint”的时序。
- `tests/test_tools.py` 与 `tests/test_session.py`
  - 对照新文件删除、已有文件恢复、按步回退和持久化测试思路。

## 学习产出

### 新增和修改代码

- `minicode_lite/session.py`：checkpoint 数据结构、序列化、选择、preview、列表与 rewind。
- `minicode_lite/tools/_shared.py`：三种编辑工具共享的写前快照入口。
- `minicode_lite/tools/write_file.py`、`edit_file.py`、`patch_file.py`：审批后、写盘前接入 checkpoint。

### 新增测试

- `tests/test_session.py`：持久化计数、新旧文件恢复、多步回退、preview、反向 rewind、越界和批量预检。
- `tests/test_tools.py`：三种写工具确实记录旧内容，审批拒绝不产生虚假快照。

### 本阶段最终能力

- 每次有 session 的文件写入都能留下持久恢复点。
- 新建、覆盖、精确编辑和多段补丁都能恢复。
- 用户可在零副作用 preview 后按步或指定 checkpoint 回退。
- rewind 自身可被下一次 rewind 撤销。
- 被篡改的越界路径不能借恢复功能写出 workspace。

## 测试验证

收尾验证命令：

```powershell
python -m pytest -q
python -m compileall -q minicode_lite
git diff --check
```

2026-07-19 的全量测试结果为：

```text
110 passed, 1 skipped
```

跳过项仍是需要显式开关和真实配置的 live Qwen 测试。重点验证：checkpoint JSON 往返和 metadata 数量；三种工具的快照时序；新文件回退删除；已有文件旧内容恢复；多次编辑按 steps 倒序恢复；preview 零副作用；反向 rewind；越界与目录目标在任何写盘前失败。

## 和真实 MiniCode-Python 的差异

### 保留的设计

- checkpoint 是 session 状态的一部分，并在文件修改前持久化。
- 支持 steps、checkpoint ID、preview 和 checkpoint 列表。
- rewind 前创建反向安全快照，使恢复操作可撤销。
- 同组安全快照按一个逻辑步骤处理。

### 简化的设计

- 只保存 UTF-8 全量文本，不处理二进制文件、权限位、时间戳和目录树。
- session 仍使用单个全量 JSON，没有 checkpoint delta。
- 当前文件工具一次只修改一个目标，普通 edit checkpoint 尚不需要跨文件 group。
- 未实现磁盘写入事务；通过整批预检缩小部分恢复风险，但极端 I/O 故障仍可能中断。

### 后续再实现的设计

- 阶段 11 用 `/checkpoints`、`/rewind-preview`、`/rewind` 暴露产品命令。
- 有真实规模数据后再考虑容量限制、快照清理、压缩与冲突检测。
- 若未来工具支持目录或二进制编辑，需要新的 checkpoint 类型而不是复用文本字段。

## 常见误区

- 误区：工具一开始就创建 checkpoint 更安全。
  - 这样无效参数、找不到替换文本或审批拒绝也会产生虚假恢复点。正确时序是所有检查和审批通过后、写盘之前。
- 误区：rewind 只需恢复最后一份旧内容。
  - 连续编辑时必须倒序应用所选快照，才能从当前状态逐层回到目标点之前。
- 误区：`existed=False` 应写回空文件。
  - 它表示修改前根本没有文件，因此正确恢复动作是删除新文件。
- 误区：session 保存的是绝对路径，所以恢复时无需再验证。
  - JSON 可能被手工篡改；任何持久化输入重新进入副作用边界时都必须按当前 workspace 验证。
- 误区：preview 先读取磁盘更准确。
  - 阶段 9 的 preview 描述计划消费的恢复点，权威来源是 session；不接触磁盘更容易保证零副作用。

## 复习提示

重点理解：为什么 checkpoint 的位置必须夹在审批与写盘之间；为什么多步恢复必须倒序；为什么 rewind 也需要 checkpoint；为什么恢复前要先整批预检。

自测问题：

1. 覆盖已有文件和创建新文件的 `existed` 分别是什么？
2. `steps=2` 时为什么不能正序写回两个旧内容？
3. 权限拒绝后如果 checkpoint 数量增加，说明哪一层时序错了？
4. 为什么同一 rewind group 不能只恢复一个成员？
5. 当前实现在哪些极端 I/O 情况下还不是真正事务？

## 面试高频问题与参考答案

### 1. checkpoint 在 agent harness 中解决什么问题？

**参考答案：** 它把不可逆的文件写入变成有恢复依据的操作。session replay 只能说明 agent 做过什么，checkpoint 额外保存修改前的磁盘状态，使错误编辑能真正回退。它属于安全与可恢复性能力，不是单纯的日志字段。

### 2. `FileCheckpoint` 为什么同时需要 `existed` 和 `previous_content`？

**参考答案：** `previous_content` 只表达文本，无法区分“原文件内容为空”和“原文件不存在”。`existed=True` 时恢复是写回旧文本，即使旧文本为空；`existed=False` 时恢复是删除后来创建的文件。这两个字段共同定义完整的旧状态。

### 3. 文件工具创建 checkpoint 的正确数据流是什么？

**参考答案：** 先验证参数和 workspace 路径，读取旧内容并计算新内容，再完成权限审批；只有确定修改会执行后，才持久化旧状态，随后写盘。这样拒绝和无效编辑不会污染恢复历史，同时快照保存失败时原文件仍未变化。

### 4. 取舍题：为什么使用全量文本快照，而不是直接复制 Git 或真实 MiniCode 的全部增量机制？

**参考答案：** 当前目标是理解最小恢复闭环，文件规模和会话长度都小。全量文本数据模型直接、可读、容易用 `tmp_path` 验证。Git 会引入仓库状态和索引语义，delta 会引入合并与损坏恢复；这些复杂度只有在性能或产品需求出现后才值得承担。

### 5. checkpoint/rewind 有哪些关键安全边界？

**参考答案：** 创建时目标必须已经过 workspace 路径检查；恢复时不能信任 JSON 中的绝对路径，要再次验证路径仍位于原 session workspace；整批目标要在任何写盘前确认不是目录。权限拒绝不能生成 checkpoint，恢复也不能用被篡改记录越界写文件。

### 6. 如何测试 preview 确实没有副作用？

**参考答案：** 在临时目录创建当前文件与包含不同旧内容的 checkpoint，调用 preview 前后读取文件并断言完全一致，同时断言 session checkpoint 列表与 metadata 未变化。测试应调用真实格式化函数，但不需要 mock 文件系统，因为 `tmp_path` 能直接观察磁盘状态。

### 7. 场景题：连续两次编辑后 `rewind(steps=2)` 只回到第一次编辑后的内容，怎样排查？

**参考答案：** 先检查两个 checkpoint 的旧内容是否分别是初始状态和第一次编辑后的状态；再检查选择结果是否包含两个；最后检查应用顺序。若按旧到新正序恢复，第二个快照会覆盖第一个，最终停在中间状态；正确做法是从最新快照向最旧快照倒序应用。

### 8. 为什么 rewind 自身也要创建反向安全 checkpoint？

**参考答案：** rewind 仍然是有副作用的文件操作，用户可能选错 steps 或目标 ID。如果简单删除已消费 checkpoint，就无法撤销这次恢复。执行前捕获当前最终状态并以同组 `kind="rewind"` 保存，下一次 rewind 就能把文件恢复到回退前。

### 9. `group_id` 解决什么问题？

**参考答案：** 一次 rewind 可能影响多个不同文件，每个文件需要自己的当前状态快照，但它们属于同一个用户动作。`group_id` 让选择逻辑把这些记录视为不可拆分的一步，防止下一次只撤销其中一个文件而让工作区进入混合状态。

### 10. 当前实现与真实 MiniCode-Python 的主要差异是什么？

**参考答案：** 核心数据契约、写前时序、preview、按步选择和反向安全快照都保留；轻量版仍用全量 JSON 和 UTF-8 文本，不做 delta、压缩、清理、复杂 autosave 与产品命令。它证明了恢复语义，但没有声称提供文件系统级事务保证。

## 下一阶段衔接

本阶段解决了：

```text
错误文件修改有持久快照，可以预览并恢复。
```

阶段 10 要解决：

```text
系统能恢复文件，但还不能把项目关键知识显式记住并注入后续任务。
```

session 已经成为消息和 checkpoint 的持久状态容器；下一阶段的 memory 将学习另一类状态：不是撤销副作用，而是保存可检索的长期知识。
