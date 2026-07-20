# 阶段 10：最小项目 memory 学习总结

## 主题

本阶段的主题是：让 MiniCode Lite 不只保存“做过什么”，还能够显式记住项目知识，并在后续任务中按需取回。

大白话讲，session 像工作录像，checkpoint 像文件修改前的备份，而 project memory 更像项目旁边的一本知识卡片册。用户把稳定事实写进卡片册，下一次提问时，harness 先找出相关卡片，再放进模型的 system prompt。

## 问题是什么

阶段 8 和阶段 9 已经能保存对话、回放过程和恢复文件，但历史数据不会自动变成模型下一轮可用的知识。本阶段具体解决：

1. 项目知识用什么最小数据结构保存？
2. 怎样保证不同 workspace 的记忆互不串用？
3. 不引入向量数据库时，怎样完成可解释的中英文关键词检索？
4. 怎样区分“memory 未配置”和“memory 已配置但本次没有命中”？
5. memory 文件损坏时，怎样避免整个 agent turn 被阻断？

## 解决方案

### 最小解决方案

- 新增 `MemoryEntry`，保存 ID、内容、创建/更新时间和标签。
- 新增 `MemoryManager`，把记忆固定保存在 workspace 下的 `.minicode-lite-memory/memory.json`。
- 使用带 `schema_version` 的全量 JSON，并通过临时文件替换完成原子保存。
- `add` 接受字符串和结构化输入；结构化输入优先转换为稳定 JSON，空内容明确拒绝。
- 检索使用英文词、数字标识符、中文连续词和中文双字片段的集合交集评分。
- headless 在构造 system prompt 前，用当前用户请求检索 project memory，并只注入本轮相关结果。
- 缺失或损坏的 memory 文件降级为空记忆，不影响正常模型调用。

### 为什么这个方案足够

阶段目标是证明 `add -> persist -> retrieve -> inject` 闭环。关键词检索结果可解释、无需外部依赖、容易用 `tmp_path` 测试；TF-IDF、BM25、向量检索、自动摘要、三层作用域和 memory pipeline 都会显著增加策略复杂度，应等真实规模和需求出现后再实现。

## 工作原理

### 心智模型

project memory 是“经过选择后长期保留的项目事实”，不是完整聊天历史，也不是当前 turn 的临时思考：

```text
显式项目知识
  -> MemoryManager.add
  -> .minicode-lite-memory/memory.json
  -> 后续用户请求
  -> MemoryManager.search
  -> memory_context
  -> build_system_prompt
  -> model adapter
```

### 核心对象解释

#### `MemoryEntry`

它是一条最小持久记忆。`entry_id` 提供稳定身份，`content` 是真正注入模型的知识，时间字段为同分排序和未来更新能力留出接口，`tags` 则让业务关键词也能参与检索。

#### `MemoryManager`

它把 memory 生命周期限制在一个已解析的 workspace 内。构造时只加载已有文件，不因普通查询创建目录；只有新增记忆时才落盘。这让“读取 memory”保持低副作用，也避免不同项目共享错误上下文。

#### `_stringify_content`

它定义输入边界。字符串会去除首尾空白；字典、列表、数字等优先转为排序稳定的 JSON；其他自定义对象退回文本表示；最终为空则抛出 `ValueError`。这样持久化层始终只处理明确字符串。

#### `_tokens` 与 `search`

`_tokens` 提取英文词、数字标识符和中文词。中文没有空格，因此额外产生双字片段，让“权限边界”可以命中“危险命令需要权限审批”。`search` 按重合关键词数量评分，完整短语额外加分，同分时新记忆优先。

#### `get_context` 与 `build_system_prompt`

`get_context` 把命中条目格式化为短列表。prompt 构建器接收三态输入：`None` 表示 memory 未配置；空字符串表示已配置但无相关记忆；非空字符串表示应注入的本轮上下文。

## 对应核心文档

参考项目路径：`D:\JavaProject\MiniCode-Python-main`

- `minicode/memory.py`
  - 对照项目 memory 的持久化、检索和 system prompt 注入职责。
  - 理解真实项目的 user/project/local 三层作用域和 TF-IDF 能力，但本阶段不复制。
- `minicode/working_memory.py`
  - working memory 保护当前任务连续性；project memory 跨 session 保存稳定项目知识，两者生命周期不同。
- `minicode/memory_pipeline.py`
  - 自动提取、筛选、更新与注入属于后续增强，本阶段只保留显式写入和确定性检索。

## 学习产出

### 新增和修改代码

- `minicode_lite/memory.py`：项目记忆数据结构、持久化、加载、关键词检索和上下文格式化。
- `minicode_lite/prompt.py`：支持注入 memory context，并表达未配置与无命中的差别。
- `minicode_lite/headless.py`：在模型调用前按当前用户请求检索项目记忆。

### 新增测试

- `tests/test_memory.py`：覆盖持久化、重载、中英文检索、结构化输入、空内容、空查询、损坏文件和 schema。
- `tests/test_prompt.py`：覆盖 memory 三态 prompt 输出。
- `tests/test_headless.py`：覆盖真实 headless 数据流中的相关记忆注入。

### 本阶段最终能力

- 项目知识可显式写入并跨进程重载。
- 后续任务能按当前请求检索相关记忆。
- 只有相关结果进入 system prompt，无命中时不会注入无关历史。
- memory 文件损坏不会拖垮正常 agent turn。
- 不同 workspace 天然使用不同的 memory 文件。

## 测试验证

收尾验证命令：

```powershell
python -m pytest -q
python -m compileall -q minicode_lite
git diff --check
```

2026-07-20 的全量测试结果为：

```text
121 passed, 1 skipped
```

跳过项仍是需要显式开关和真实配置的 live Qwen 测试。重点验证：写入后 JSON 可重载；关键词排序和中文短查询；非字符串稳定转换；空内容拒绝；损坏 JSON 安全降级；prompt 三态；headless 按用户请求注入相关 project memory。

## 和真实 MiniCode-Python 的差异

### 保留的设计

- memory 是独立于 session 的长期状态，并按 workspace 组织。
- 持久化数据带 schema，检索结果可注入 system prompt。
- memory 故障采用降级策略，不应让主 agent loop 崩溃。
- working memory 与 project memory 保持不同职责。

### 简化的设计

- 只有 project scope，没有 user scope 和 local scope。
- 使用全量单文件 JSON，没有索引缓存、并发锁、备份恢复和增量更新。
- 检索只做关键词集合交集，没有 TF-IDF、BM25、向量检索或 reranker。
- 当前只支持新增，不支持更新、删除、去重、使用次数和关联图。
- 记忆必须由代码显式写入，尚未从对话或工具结果自动提取。

### 后续再实现的设计

- 阶段 11 用 `/memory` 暴露查看或管理入口。
- 出现真实检索质量问题后，再考虑 TF-IDF、BM25 或向量检索。
- 自动提取和整理应进入独立 memory pipeline，并配套误写、覆盖和隐私测试。
- 多作用域出现前，需要先定义优先级、共享边界和版本控制策略。

## 常见误区

- 误区：session 历史就是 memory。
  - session 保存一次工作的原始过程；memory 保存经过选择、适合后续复用的稳定知识。把全部历史注入会增加噪声和上下文成本。
- 误区：memory 越多，模型表现越好。
  - 无关或过期记忆会误导模型，因此本阶段按当前请求检索，只注入命中内容。
- 误区：working memory 和 project memory 只是两个文件名。
  - working memory 服务当前任务连续性，生命周期短；project memory 跨 session 保存项目事实，生命周期长。
- 误区：中文检索直接按空格切词就够了。
  - 中文句子通常没有空格，本阶段用连续词和双字片段补足最小匹配能力。
- 误区：memory JSON 损坏就应该让程序立即退出。
  - 记忆是增强上下文，不是执行主链路的唯一事实来源；轻量版选择安全降级，后续可增加诊断和备份恢复。

## 复习提示

重点理解：为什么 memory 独立于 session；为什么检索发生在 prompt 构建之前；为什么 prompt 需要区分未配置和无命中；为什么当前关键词方案是教学阶段的合理取舍。

自测问题：

1. 相同内容写入两个不同 workspace 后，为什么不会串用？
2. 空字符串作为 `memory_context` 与 `None` 有什么语义差别？
3. “权限边界”为什么能命中“权限审批”？
4. 损坏 memory 文件为什么不应阻止普通 headless turn？
5. 什么时候关键词检索会不够，需要升级检索算法？

## 面试高频问题与参考答案

### 1. project memory 在 agent harness 中解决什么问题？

**参考答案：** 它解决跨 session 复用稳定项目知识的问题。session 保存原始对话和工具过程，但下一轮模型不会自动理解全部历史；project memory 把被选择的事实持久化，并在相关任务出现时检索注入，从而让模型遵守已有约定和设计决策。

### 2. `MemoryEntry` 为什么需要 ID、时间和标签，而不只保存一段文本？

**参考答案：** 文本是当前最小功能，但稳定 ID 支撑未来更新和删除，时间字段支撑同分排序与过期策略，标签让内容之外的业务术语参与检索。这些字段成本很低，却避免下一阶段为基本管理能力重做数据格式。

### 3. 一条用户请求如何得到 memory context？

**参考答案：** headless 先确定 workspace 并加载 `MemoryManager`，再用已经清理的用户请求调用 `search`；检索结果由 `get_context` 格式化，传给 `build_system_prompt`；最终 system 消息位于 user 消息之前进入 model adapter。没有命中时仍明确表示 memory 已配置。

### 4. 取舍题：为什么阶段 10 不直接实现真实 MiniCode 的 TF-IDF、三层 memory 和自动 pipeline？

**参考答案：** 当前要学习的是记忆闭环的职责边界，不是检索平台。关键词交集已经能验证写入、持久化、查询和注入；三层作用域会引入优先级，TF-IDF 会引入语料统计，自动 pipeline 会引入误提取和更新策略。提前加入会让问题难以定位，也不符合先跑最小闭环的原则。

### 5. memory 的异常与安全边界是什么？

**参考答案：** workspace 解析后决定唯一存储位置，管理器不接受任意外部 memory 路径；持久化始终写入项目子目录；空内容被拒绝；损坏 JSON 被视为空记忆，不进入 prompt。当前仍缺少容量限制、敏感信息过滤和并发锁，这些是后续需要补的边界。

### 6. 为什么非字符串内容优先转换为 JSON，而不是直接调用 `str`？

**参考答案：** JSON 对字典、列表、数字和布尔值有稳定、跨语言的表示，字典键排序后测试和持久化结果可重复。`str(dict)` 更依赖 Python 表示形式。只有对象无法 JSON 序列化时，轻量版才退回 `str`，以满足教学阶段的宽容输入边界。

### 7. 怎样测试 memory 注入不是只测到了格式化函数？

**参考答案：** 除了单测 `build_system_prompt`，还要在临时 workspace 写入记忆，用 `ScriptedModel` 执行真实 `run_headless`，最后检查模型实际收到的第一条 system 消息。这样覆盖了加载、检索、格式化、prompt 构建和 model 调用前消息顺序。

### 8. 场景题：memory 文件里有“文件编辑前创建 checkpoint”，但询问 checkpoint 规则时没有注入，怎样排查？

**参考答案：** 先确认运行的 cwd 与写入记忆的 workspace 相同；再检查 JSON 能否加载和 schema 是否为 1；然后直接调用 `search` 查看分词是否有交集；最后检查 headless 是否把原用户请求传给 `get_context`，并把结果传给 prompt。若英文大小写不同不影响命中，若使用完全不同的同义词，当前关键词算法可能确实无法召回。

### 9. `memory_context=None` 和 `memory_context=""` 为什么要区分？

**参考答案：** `None` 表示调用方根本没有配置 memory 能力，空字符串表示 memory 已正常加载和检索，只是本轮没有相关结果。区分两者有利于模型理解运行时能力，也为后续 readiness 诊断提供准确状态。

### 10. 当前实现与真实 MiniCode-Python 的主要差异是什么？

**参考答案：** 轻量版保留了 project memory 持久化、相关检索和 prompt 注入主线，但只有单一 scope、单文件 JSON 和关键词评分。真实项目还包括 user/project/local 分层、更复杂的相关性评分、使用统计、关联、整理与注入 pipeline。当前实现是可测试的骨架，不是完整知识库。

## 下一阶段衔接

本阶段解决了：

```text
项目知识可以显式保存，并在相关后续任务中进入模型上下文。
```

阶段 11 要解决：

```text
session、checkpoint 和 memory 已有内部 API，但用户还缺少统一的本地命令来查看和操作它们。
```

`MemoryManager` 已经提供稳定的加载、检索和状态数据，下一阶段可以在不改变存储核心的前提下增加 `/memory` 等产品命令。
