# 阶段 08：session 持久化和 replay 学习总结

## 主题

本阶段的主题是：把一次 agent turn 从“程序退出就消失的内存列表”变成可保存、可检查、可筛选、可回放的运行记录。

大白话讲，agent loop 已经能做事，但此前只能看到最后一句回答。模型为什么调用工具、工具返回了什么、失败发生在哪一步，进程退出后都无法追溯。session 就像 harness 的运行档案：既保存模型继续工作所需的原始消息，也生成适合人阅读的 transcript。

## 问题是什么

阶段 8 解决三个具体问题：

1. turn 结束后，完整消息历史如何可靠落盘？
2. 多个项目产生的 session 如何按 workspace 隔离和找到最新记录？
3. 原始消息协议如何转换成用户能顺序阅读的 replay，而不丢失工具调用与结果的配对？

如果只保存最终回答，工具错误和中间决策不可观察；如果只保存 UI 文本，后续恢复模型上下文时又缺少结构化字段。因此需要同时保留 `messages` 和从它派生的 `transcript_entries`。

## 解决方案

### 最小解决方案

- 用 `SessionData` 保存 session 身份、时间、workspace、完整 messages 和 transcript。
- 用 `SessionMetadata` 保存列表页需要的轻量摘要。
- 每个 session 使用一个全量 JSON 文件，暂不做 delta 增量保存。
- 保存前始终从 messages 重新生成 transcript，避免两份状态分别追加后发生漂移。
- workspace 在创建时解析成绝对路径，列表过滤时按平台路径大小写规则比较。
- 保存采用“同目录临时文件 -> replace”流程，降低中断产生半截 JSON 的概率。
- headless 在模型 turn 的 `finally` 中保存；成功时保存完整结果，异常时至少保存输入上下文。
- session ID 先校验再拼接路径，阻断 `../` 形式的目录穿越。

### 为什么当前不做增量保存

阶段 8 的学习目标是先证明状态契约和 replay 数据流成立。单文件全量 JSON 易于打开、调试和测试，也没有 base snapshot 与 delta 合并的一致性问题。真实 MiniCode 的增量保存适合长会话和高频 autosave，但会同时引入脏状态跟踪、合并、压缩和损坏恢复，不属于当前最小闭环。

## 工作原理

### 心智模型

```text
用户 prompt
  -> agent loop 追加 tool call / tool result / assistant
  -> 完整 ChatMessage 列表（权威状态）
  -> build_transcript（展示投影）
  -> SessionData.update_metadata（列表摘要）
  -> 全量 JSON 原子替换
  -> load / list / latest / inspect / replay
```

关键点是单一事实来源：`messages` 决定 transcript，而不是两边同时手工维护。这样只要 agent loop 的消息协议正确，持久化与回放看到的顺序就一致。

### 核心对象解释

#### `SessionData`

它代表可完整恢复的一份会话状态。`messages` 保留 system、user、assistant、tool call 和 tool result 的原始结构；`transcript_entries` 是面向展示的派生时间线；`workspace` 表明这份记录属于哪个项目。

#### `SessionMetadata`

它只保存列表所需信息：ID、创建/更新时间、工作区、首条用户消息和计数。调用方列出 session 时无需理解完整消息内容。当前实现扫描完整 JSON 后取 metadata，未来可替换成独立索引而不改变上层 API。

#### `build_transcript`

它跳过 system prompt，依次转换实际 turn 事件。工具请求保留 `toolName`、`toolUseId` 和结构化 input；工具结果保留同一个 ID、正文和 `isError`。因此 replay 能表达“谁调用了哪个工具、结果是否失败”，同时原始 messages 仍可供未来 resume 使用。

#### 保存与加载函数

`save_session` 刷新 transcript 和 metadata，将 schema version 与完整状态写入临时文件，再替换目标文件。`load_session` 校验 schema、ID 和字段类型；不存在或损坏时返回 `None`。`list_sessions` 会跳过损坏记录，避免一份坏文件阻塞全部历史。

#### headless 接入

本地 `/tools`、`/read` 命令没有进入 agent loop，不创建 session。普通模型任务在进入 loop 前创建 session 并记录 system/user；成功后替换为完整返回历史；`finally` 负责落盘。主 CLI 已复用 headless，因此无需再维护第二套保存逻辑。

## 当前核心流程

```text
run_headless
  -> create_new_session
  -> run_agent_turn
  -> session.messages = result_messages
  -> save_session
       -> build_transcript
       -> update_metadata
       -> JSON temporary file
       -> replace final file
```

回放流程：

```text
session_id
  -> 安全 ID 校验
  -> load_session
  -> transcript_entries（保持原始顺序）
  -> format_session_replay
  -> user / tool call / tool result / assistant 时间线
```

## 对应核心文档

参考项目路径：`D:\JavaProject\MiniCode-Python-main`

- `minicode/session.py`
  - 对照了 `SessionData`、`SessionMetadata`、全量状态结构、workspace 过滤、latest、inspect 和 replay。
  - 真实实现已有 delta、checkpoint、运行时摘要和更多产品面字段，本阶段只保留 session/replay 主路径。
- `tests/test_session.py`
  - 对照了 monkeypatch session 目录、JSON 往返、workspace 过滤和格式化测试方法。
- `minicode/tui/transcript.py`
  - 只借鉴 transcript 作为展示时间线的职责，没有引入 TUI 渲染和生命周期管理。

## 学习产出

### 新增代码

- `minicode_lite/session.py`
  - session 数据结构、全量 JSON 保存/加载、列表/latest、inspect/replay 和 transcript 派生。
- `minicode_lite/headless.py`
  - 普通模型 turn 结束时自动保存 session；主 CLI 通过复用 headless 同时获得该能力。

### 新增测试

- `tests/test_session.py`
  - 覆盖创建、完整 JSON 往返、workspace 过滤、latest、工具事件配对、inspect/replay、损坏文件和路径穿越。
- `tests/test_headless.py`
  - 覆盖 model -> tool -> model -> final 后完整 messages 与 transcript 自动落盘。

### 本阶段最终能力

- agent turn 退出后仍能加载完整消息历史。
- 能按 workspace 查找 session 并获得最新记录。
- 能以可读时间线回放 user、assistant、工具请求和工具结果。
- 单个损坏文件不会让全部 session 列表不可用。

## 测试验证

收尾执行：

```powershell
python -m pytest -q
python -m compileall -q minicode_lite
git diff --check
```

2026-07-18 的全量测试结果为：

```text
98 passed, 1 skipped
```

跳过项仍是需要显式开关和真实配置的 live Qwen 测试。重点验证行为包括：

- UTF-8 内容和结构化工具输入可以完整 JSON 往返。
- workspace 过滤使用规范化绝对路径。
- latest 按 `updated_at` 选择。
- replay 同时包含 user、assistant 和 tool result。
- 非法 session ID 不能逃逸 session 目录。
- headless 自动保存真实 agent turn。

## 和真实 MiniCode-Python 的差异

### 保留的设计

- 原始 messages 与 transcript 同时持久化。
- metadata 与完整 session 状态分工。
- 支持 workspace 过滤、latest、inspect 和 replay。
- 损坏或不存在的 session 用可预期结果隔离。

### 简化的设计

- 每次都保存全量 JSON，没有 delta 文件和周期性 consolidation。
- 没有独立 session index，列表通过扫描 JSON 实现。
- 每个 headless 调用创建一个新 session，尚未实现跨进程 resume 和多轮追加。
- transcript 从消息历史一次性派生，没有 TUI 实时事件、stream chunk 或权限事件。
- 异常 turn 只能保存 loop 开始前的输入，因为当前 agent loop 对调用方采用返回副本语义。

### 后续再实现的设计

- 阶段 9 在 session 上增加 file checkpoint 和 rewind。
- 阶段 11 增加 `/session`、`/sessions` 和 `/session-replay` 产品命令。
- 长会话出现真实性能需求后，再考虑索引、delta、autosave 和清理策略。

## 常见误区

- 误区 1：session 就是聊天文本文件。
  - 正确理解：它还必须保留工具名、调用 ID、结构化输入和错误状态，未来才能恢复模型上下文和检查工具链。
- 误区 2：messages 和 transcript 应由两个调用路径分别追加。
  - 正确理解：双写容易漏事件或顺序不一致；当前以 messages 为权威来源，保存时派生 transcript。
- 误区 3：按字符串直接比较 workspace 足够。
  - 正确理解：相对路径、`..` 和 Windows 大小写会让同一目录出现不同文本，创建与过滤都要规范化。
- 误区 4：JSON 写入成功返回前不需要考虑中断。
  - 正确理解：直接覆盖目标文件可能留下半截内容；临时文件写完后替换能缩短不一致窗口。
- 误区 5：一个 session 损坏就应该让列表抛异常。
  - 正确理解：历史记录彼此独立，列表应跳过坏记录，让其他可用记录仍能被访问。

## 复习提示

重点重新理解：

- 为什么 messages 是权威状态而 transcript 是投影？
- `toolUseId` 为什么必须同时出现在工具请求和结果里？
- workspace 为什么要在 session 创建时规范化？
- 全量 JSON 与 delta 保存分别优化什么？
- `finally` 保存能保证什么，又不能保证什么？

自测问题：

1. 如果 replay 缺少 tool result，应先检查 agent loop 还是格式化函数？为什么？
2. 两个相对路径指向同一目录时，workspace 过滤怎样保持一致？
3. 为什么损坏 JSON 返回 `None`，非法 session ID 却抛 `ValueError`？
4. 未来 resume 时应该复用 messages 还是 transcript？
5. 全量保存何时会成为性能问题？

## 面试高频问题与参考答案

### 1. session 在 agent harness 中解决的核心问题是什么？

**参考答案：** session 把一次运行的消息、工具活动和摘要从易失内存变成持久状态，使任务可检查、可回放，并为后续 resume、checkpoint 和 memory 提供归属边界。只返回最终回答无法解释执行过程，也无法在进程重启后恢复模型需要的结构化上下文。

### 2. `SessionData` 和 `SessionMetadata` 为什么要分开？

**参考答案：** `SessionData` 是完整状态，包含可能很大的 messages 和 transcript；`SessionMetadata` 是列表摘要，只关心 ID、时间、工作区、标题和计数。分开后，未来可以增加独立索引，让列举历史不必加载全部正文，同时保持完整状态模型不变。当前最小实现仍扫描 JSON，但已经建立了正确职责边界。

### 3. 为什么 transcript 应从 messages 派生，而不是独立维护？

**参考答案：** messages 是 agent loop 真正消费和产出的权威协议，已经包含事件顺序及工具配对信息。如果两个列表分别追加，异常分支或新增角色很容易只更新一边。保存时从 messages 重新派生 transcript，可以消除双写漂移；代价是每次全量转换，但阶段 8 的会话规模下更简单可靠。

### 4. 设计取舍题：为什么阶段 8 选择全量 JSON，而不复制真实 MiniCode 的 delta 保存？

**参考答案：** 当前先验证持久化契约、workspace 过滤和 replay，数据量小，全量 JSON 可直接检查且故障面少。delta 会引入 offset、脏状态、合并周期、重复应用和损坏恢复。等长会话的性能测试证明全量序列化成为瓶颈后再加入增量机制，能避免为尚不存在的问题增加一致性复杂度。

### 5. session 持久化有哪些安全边界？

**参考答案：** 首先要校验 session ID，不能让 `../` 被拼成目录外路径；其次 session 默认放在系统用户临时区而不是仓库，并可用 `MINICODE_LITE_SESSIONS_DIR` 指定持久目录，避免真实对话和工具输出被误提交；再次不能在 replay 中误认为内容可信，历史仍可能包含模型或工具产生的数据。当前实现没有加密，因此也不应把 API key 等秘密写入消息。

### 6. 如何测试 session，而不污染开发者真实历史？

**参考答案：** 测试通过 monkeypatch 把模块级 `SESSIONS_DIR` 指向 pytest 的 `tmp_path`。然后使用真实 JSON 保存和加载，而不是 mock 文件系统，这样能验证编码、文件名、排序和损坏处理。每个测试得到独立目录，既无共享状态，也无需清理用户目录。

### 7. 场景题：session 文件存在，但 `get_latest_session` 返回了 `None`，如何排查？

**参考答案：** 先调用 `list_sessions()` 判断文件是否因 JSON 损坏、schema 不匹配或非法文件名被跳过；再检查 workspace 是否在创建和查询时解析成同一绝对路径，Windows 上还要考虑大小写；然后核对 metadata 的 `updated_at` 与 session ID。最后单独调用 `load_session(id)`，区分“选不到记录”和“选到但加载失败”。

### 8. 工具调用在 replay 中怎样保持因果关系？

**参考答案：** assistant tool call 和 tool result 保存相同的 `toolUseId`，并同时保留 `toolName`。顺序告诉读者先请求后观察，ID 则在并行调用或多次调用同一工具时提供稳定配对。只按工具名匹配会在重复调用时产生歧义，只有正文也无法说明结果属于哪个请求。

### 9. 保存放在 `finally` 中有什么收益和限制？

**参考答案：** 收益是模型或工具路径抛异常时仍会执行落盘，不会完全失去失败任务的输入上下文；成功路径则保存完整返回历史。限制是当前 agent loop 在内部副本上追加消息，异常时没有把部分副本交回调用方，所以只能保存进入 loop 前的 system/user。要记录异常前的每个中间事件，未来需要事件回调或共享 session store。

### 10. 当前实现与真实 MiniCode-Python 的 session 有哪些主要差异？

**参考答案：** 当前只有全量 JSON、基本 metadata、消息派生 transcript 和简单列表；真实实现还有增量 delta、索引、checkpoint、更多运行时与产品面摘要、autosave 和清理策略。阶段 8 保留数据职责与核心 API，后置性能和产品复杂度，方便先用测试证明最小持久化闭环正确。

## 下一阶段衔接

本阶段解决了：

```text
agent turn 可以在退出后被加载、检查和回放。
```

阶段 9 要解决：

```text
会话知道“发生过修改”，但还不能把错误的文件修改恢复到之前状态。
```

本阶段产物会这样支撑下一阶段：

- `SessionData` 提供 checkpoint 的自然归属对象和持久化文件。
- 全量 JSON 可以直接扩展 checkpoints 字段，先验证 write -> snapshot -> rewind。
- `format_session_inspect` 和 replay 为后续展示恢复点与回退结果预留了产品面。
