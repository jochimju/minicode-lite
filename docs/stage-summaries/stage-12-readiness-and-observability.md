# 阶段 12：readiness 和可观测性学习总结

## 主题

本阶段的主题是：让 harness 在真正开始工作前说明本地条件是否就绪，并在工作过程中留下不泄密的关键诊断事件。

大白话讲，阶段 11 让用户能操作 session、memory 和 rewind，但系统仍不会系统回答“为什么现在能工作”或“这轮为什么停了”。阶段 12 给运行时加上仪表盘和行车记录：readiness 看启动条件，logging 看工具与 turn 的关键结果。

## 问题是什么

### 为什么要有这个阶段

模型调用失败不一定是模型本身的问题，也可能是 Python 版本、工作目录、工具注册或配置缺失。若所有失败都等到 agent loop 深处才暴露，用户只能看到模糊异常，开发者也难以区分环境问题、工具问题和循环停止。

另一方面，只“打印更多文本”并不等于可观测。日志需要稳定字段、明确事件边界和敏感信息保护，否则既不能可靠检索，还可能把源码、命令参数或 API key 写入磁盘。

### 本阶段具体要解决的问题

1. 用一次本地只读检查回答 Python、cwd、工具和模型路径是否可用。
2. 区分真实 Qwen ready、mock fallback warning 和真正 blocked。
3. 同时提供人读文本与机器可读 JSON，并固定 schema 版本。
4. 在工具统一执行边界记录名称、结果和耗时。
5. 在 agent loop 的所有正常停止出口记录 stop reason 和步数。
6. 保证诊断不发起 provider 请求，也不记录工具输入、输出和密钥。

## 解决方案

### 最小解决方案

- 新增 `readiness.py`，用 `ReadinessCheck` 和 `ReadinessReport` 表达检查结果。
- 固定四项检查：Python、cwd、工具注册、模型配置或 mock fallback。
- 使用 `ready`、`warning`、`blocked` 三级汇总，严重程度为 `blocked > warning > ready`。
- 提供 `/readiness` 与 `/readiness --json`，在模型创建前由本地命令层处理。
- 新增 `logging_config.py`，提供工具执行和 turn 停止两个日志函数。
- 在 `ToolRegistry.execute` 和 `agent_loop` 的权威边界埋点，而不是在每个具体工具或 UI 中重复记录。
- 用标准库 logging 的 `extra` 字段提供 `tool_name`、`success`、`duration_ms`、`stop_reason` 和 `steps`。

### 为什么这个方案足够

阶段 12 的目标是建立最小诊断闭环，而不是复制真实 MiniCode 的完整运维系统。当前检查已经覆盖 agent 启动的四个基础依赖；日志已经覆盖“行动”和“停止”两个关键事件。文件轮转、完整 JSON formatter、provider live smoke、release artifact bundle 和 turn phase 策略分别属于更成熟的部署面、阶段 16 和阶段 13，不应提前耦合进来。

## 工作原理

### 心智模型

readiness 是“开始前的静态预检”，回答本地已知条件；logging 是“运行中的事件证据”，回答刚才发生了什么。readiness 为 `ready` 也不承诺网络一定可达，因为它没有调用 provider；工具日志为 success 也只说明该工具返回 `ok=True`，不替模型判断任务最终是否完成。

### 核心对象解释

#### `ReadinessCheck`

它表示一个原子检查，包含稳定名称、三级状态和安全摘要。稳定名称供 JSON 消费者判断，摘要供用户理解原因。把检查拆开后，整体状态不需要靠解析一段大文本得到。

#### `ReadinessReport`

它保存 schema 版本、整体状态、当前模型模式、工作区、Python 版本和检查数组。`to_dict()` 显式把检查集合转成 JSON 数组，避免 Python 内部类型泄漏到对外契约。

#### `build_readiness_report`

它解析目标 workspace，读取该 workspace 的 `.env`，执行四项纯本地检查，再按最严重状态汇总。真实模型三项配置完整时 mode 为 `qwen`；不完整时 mode 为 `mock`，模型检查为 warning，因为现有 `model_registry` 能回退到 mock。

#### `format_readiness_text` 与 `format_readiness_json`

文本格式面向终端快速阅读，JSON 格式面向测试、CI 和后续 release gate。JSON 带 `schema_version=1.0` 并排序键，使字段变化和快照差异更容易发现。

#### `log_tool_execution`

该函数只接收工具名、成功标志和耗时。它刻意不接收输入与输出，从函数签名上减少误写敏感内容的机会。

#### `log_turn_stop`

该函数记录停止原因和模型步数。当前原因包括 `assistant_final`、`empty_response`、`unsupported_step` 和 `max_steps`，让开发者无需反向猜测最后一条消息为什么出现。

#### `ToolRegistry.execute` 的日志边界

未知工具、输入校验失败、runner 返回失败和 runner 异常都在注册表统一转换为 `ToolResult`，因此注册表也是记录最终工具结果的唯一可靠位置。在具体工具里埋点会漏掉未知工具和校验失败，还会产生重复日志。

### 当前核心流程

```text
/readiness [--json]
  -> 本地命令路由
  -> build_readiness_report
  -> Python / cwd / tools / model checks
  -> ready | warning | blocked
  -> text | versioned JSON
```

```text
model tool call
  -> ToolRegistry.execute 开始单调计时
  -> 查找 -> 校验 -> runner -> ToolResult
  -> tool_execution 日志（名称、成功、耗时）
  -> 结果写回 agent history
  -> assistant final 或安全停止
  -> turn_stop 日志（原因、步数）
```

## 对应核心文档

参考项目路径：`D:\JavaProject\MiniCode-Python-main`

- `minicode/readiness.py`
  - 学习 readiness 状态排序、文本/JSON 双输出和只读诊断入口。
  - 没有复制 fallback patch、repair bundle 和 release gate 等高级产品面。
- `minicode/product_surfaces.py`
  - 学习把独立检查汇总为 report，并明确 provider 本地配置与 live smoke 的区别。
- `minicode/logging_config.py`
  - 学习统一 logger 命名空间、结构化 extra 字段和工具执行日志。
  - 当前只保留最小事件函数，没有复制文件轮转与全局 setup。
- `benchmarks/release_readiness.py` / `minicode/release_readiness.py`
  - 只理解 release gate 需要消费稳定 readiness artifact，本阶段不实现发布级 bundle。

## 学习产出

### 新增代码

- `minicode_lite/readiness.py`
  - 四项本地检查、三级状态汇总、文本和 JSON 格式。
- `minicode_lite/logging_config.py`
  - 安全的工具执行日志、turn stop 日志和单调耗时工具。
- `minicode_lite/tooling.py`
  - 在统一执行边界记录所有可恢复工具结果。
- `minicode_lite/agent_loop.py`
  - 在正常 final 与各安全停止出口记录明确原因。
- `minicode_lite/cli_commands.py`
  - 新增 `/readiness [--json]` 本地命令。
- `minicode_lite/main.py`、`minicode_lite/headless.py`
  - 让参数解析器正确接受 readiness 的 `--json` 选项，并拒绝错误组合。

### 新增测试

- `tests/test_readiness.py`
  - 固定 JSON schema、Qwen ready、mock warning、空工具 blocked 和无效 cwd blocked。
- `tests/test_observability.py`
  - 验证工具成功/失败结构化字段、敏感输入输出不入日志，以及 turn stop reason。
- `tests/test_headless.py`、`tests/test_cli_stage5.py`
  - 验证 readiness 在模型创建前执行，且真实 CLI 可接收 `--json`。

### 新增文档

- `README.md`
  - 增加 readiness 命令速查和 JSON 示例。
- `docs/stage-summaries/stage-12-readiness-and-observability.md`
  - 保存本阶段心智模型、实现细节、差异与题库。

### 本阶段最终能力

- 用户能离线查看运行时为何 ready、warning 或 blocked。
- mock fallback 被明确表达为可工作但降级的 warning，而非伪装成真实 provider ready。
- CI 可消费带版本号的 JSON schema。
- 每次工具执行和每个正常 turn 停止都有可检索结构化字段。
- 日志不会记录工具输入、工具输出或 API key。

## 测试验证

执行的验证命令：

```powershell
python -m pytest -q
python -m compileall -q minicode_lite
git diff --check
python -m minicode_lite /readiness
python -m minicode_lite /readiness --json
```

2026-07-20 的全量结果：

```text
147 passed, 1 skipped
```

跳过项仍是必须显式启用并使用真实配置的 live Qwen 测试。手工 smoke 同时验证了文本输出和 JSON 输出；本机配置完整时报告为 `ready/qwen`，但摘要明确说明没有进行 live connectivity test。

重点验证行为：

- JSON 顶层字段与每项 check 字段固定，schema version 为 `1.0`。
- 缺 provider 配置时为 `warning/mock`，不会崩溃或错误标为 blocked。
- 空注册表和无效 cwd 能把整体状态提升为 blocked。
- `/readiness --json` 不创建 model adapter。
- 工具日志包含名称、成功状态和非负耗时，不包含输入输出。
- final 与 max steps 能记录不同 stop reason。

## 和真实 MiniCode-Python 的差异

### 保留的设计

- readiness 是只读本地预检，不把“配置完整”冒充成“线上请求成功”。
- 状态分级并提供文本与 JSON 两种产品面。
- 关键路径通过统一 logging helper 记录结构化字段。
- 敏感信息不进入诊断报告和工具日志。

### 简化的设计

- 只检查 Python、cwd、工具和单一 Qwen/mock 模型路径。
- 没有 fallback 候选排序、风险范围、修复计划、patch preview 或 artifact manifest。
- logging 默认不创建 console/file handler，也没有轮转和自定义 JSON formatter。
- 没有 token、成本、session 事件、权限事件和 provider request ID 日志。
- turn 日志只有 stop reason；phase 和 verification 留给阶段 13。

### 后续再实现的设计

- 阶段 13 用 turn kernel 表达 phase、verification 和 widening，并扩展 turn 诊断。
- 阶段 16 才把 readiness JSON 纳入 release checklist 和端到端 gate。
- 真正需要长期运行时再增加日志 handler、文件轮转、保留策略和结构化 formatter。
- provider live smoke 必须保持显式、可计费、可失败，不能混入默认本地预检。

## 常见误区

- 误区：`ready` 表示真实模型一定能请求成功。
  - readiness 只验证本地配置完整性；网络、额度、服务状态要由显式 live smoke 验证。
- 误区：缺少 API key 就必须 blocked。
  - 当前 harness 有稳定 mock fallback，仍可完成教学闭环，所以是 warning/mock；若连 fallback 都没有才应 blocked。
- 误区：日志越详细越利于排查。
  - 工具输入输出可能包含源码、命令和密钥。先记录稳定元数据，需要详情时从受保护的 session/replay 获取。
- 误区：在每个工具 runner 里分别记录日志最直观。
  - 这样会漏掉未知工具和 validator 失败，也会使字段漂移。统一注册表才拥有所有结果分支。
- 误区：用系统时间相减就能可靠计算耗时。
  - 系统时间可能被校准；持续时间应使用单调时钟。

## 复习提示

下次复习时，重点理解：

- 为什么 readiness 与 live provider smoke 必须分开。
- 为什么 mock fallback 是 warning 而不是 blocked 或 ready。
- 为什么 JSON 需要 schema version 和稳定名称。
- 为什么 ToolRegistry 与 loop 停止出口是两个权威日志边界。
- 为什么日志函数签名不接收工具输入输出。

可以尝试自己回答：

1. 如果 Python 通过、cwd 通过、工具为空、mock 可用，整体状态是什么？
2. `/readiness --json` 为什么必须在 model adapter 创建前执行？
3. validator 失败为什么仍能产生一条完整的工具日志？
4. readiness 报告为 Qwen ready 后，下一步怎样验证真实服务？
5. 阶段 13 可以怎样复用 stop reason 扩展 phase 诊断？

## 面试高频问题与参考答案

### 1. readiness 在 agent harness 中解决什么问题？

**参考答案：** readiness 把运行前可验证的依赖状态集中成结构化报告，让用户在进入昂贵或复杂的模型循环前知道系统能否工作、缺少什么。它检查本地事实，不执行真实任务，因此能快速区分环境错误与运行时错误。边界是它不能证明外部 provider 在线，只能说明本地调用条件是否完整。

### 2. 为什么当前实现使用 ready、warning、blocked 三级状态？

**参考答案：** 三级状态能区分完全可用、可降级工作和无法开始。真实 Qwen 配置完整且其他检查通过是 ready；Qwen 缺配置但 mock fallback 可用是 warning；cwd 无效或工具为空是 blocked。若只有布尔值，mock 降级要么被误判为失败，要么被误判为完整就绪，都会丢失重要信息。

### 3. `ReadinessCheck` 与 `ReadinessReport` 如何分工？

**参考答案：** `ReadinessCheck` 表示单项事实，负责稳定名称、状态和摘要；`ReadinessReport` 表示一次检查快照，负责整体状态、运行模式、环境元数据和检查集合。整体状态由所有 check 按严重程度归并。拆分后新增检查不需要改变消费者解析一段总文本的方式。

### 4. 取舍题：为什么不直接复制真实 MiniCode 的完整 readiness 和 release bundle？

**参考答案：** 当前阶段只需要建立“本地预检 -> 可解释状态 -> 文本/JSON 输出”的最小闭环。真实实现还处理多 provider fallback、修复计划、patch preview、artifact manifest 和发布门禁，这些依赖本项目尚未实现的产品能力。现在复制会增加大量没有真实数据来源的空结构，也模糊 readiness 与阶段 16 release gate 的边界。

### 5. 为什么模型配置不完整时是 warning 而不是 blocked？

**参考答案：** 因为 `model_registry` 已有确定性的 `MockModelAdapter` fallback，离线教学、测试和最小 agent loop 仍能运行。readiness 必须报告系统真实能力，而不是只检查理想生产路径。不过 warning 也不能改成 ready，因为用户需要知道当前回答不是由真实 Qwen 生成的。

### 6. 为什么工具执行日志应该放在 `ToolRegistry.execute`？

**参考答案：** 注册表拥有工具执行的完整控制流：未知名称、validator 失败、runner 成功、runner 返回失败和 runner 异常都经过这里。若日志放进各 runner，会漏掉 runner 之前的失败，还会让不同工具采用不同字段。统一边界能保证一次调用只产生同形事件，并且最终 success 与返回给 loop 的 `ToolResult.ok` 一致。

### 7. 安全题：为什么工具日志不记录 input 和 output？

**参考答案：** input 可能含命令、文件内容、路径或凭据，output 可能含源码、环境信息和 provider 错误正文。把它们默认写入日志会扩大敏感数据的存储范围和保留时间。当前诊断只需工具名、结果和耗时；需要业务详情时应使用已有且受 workspace 约束的 session/replay，而不是无边界复制到日志。

### 8. 测试 readiness 为什么要注入 `RuntimeConfig` 而不是依赖开发机 `.env`？

**参考答案：** readiness 的分支取决于配置完整性，开发机环境会使测试在不同机器上得到 ready 或 warning，甚至误触真实 provider 路径。测试直接构造完整和缺失配置，可确定性覆盖两个模式，并断言密钥不出现在 JSON。入口测试再用环境隔离验证实际路由，从而兼顾单元逻辑和集成顺序。

### 9. 场景题：报告是 `ready/qwen`，但实际任务仍报 provider request failed，如何排查？

**参考答案：** 先确认 readiness 摘要中的“live connectivity was not tested”，不要把两者视为矛盾。然后运行显式 live smoke，依次检查 DNS/网络、base URL、认证、模型名、配额和服务状态；同时保持错误输出脱敏。若本地配置后来变更，应重新运行 readiness。这个场景说明 readiness 负责本地前置条件，live smoke 才负责外部通道。

### 10. 场景题：一个工具校验失败，但日志显示 success=true，应该从哪里修？

**参考答案：** success 必须来自最终 `ToolResult.ok`，而不是“runner 是否被调用”或“execute 是否抛异常”。应检查 `ToolRegistry.execute` 是否在所有分支先构造统一 result，再在单一出口记录日志；validator 失败应构造 `ok=False`。测试要同时断言返回结果与日志 record 的 success，防止两个事实源漂移。

### 11. 为什么 JSON schema 要包含版本号？

**参考答案：** 后续 CI、release gate 或外部脚本会按字段读取 readiness。新增兼容字段通常可以保持版本，但字段改名、类型改变或语义改变需要升级 schema，让消费者显式适配，而不是静默误读。版本号不是装饰，它是机器接口演进的协商点。

### 12. 当前实现与真实 MiniCode-Python 的核心差异是什么？

**参考答案：** 轻量版保留了本地预检、分级状态、文本/JSON 双输出、统一结构化日志和敏感信息保护；简化为单一 Qwen/mock 路径和两个关键日志事件。真实项目还覆盖多 provider fallback、风险与修复计划、release artifacts、日志轮转、API 成本和更多产品状态。轻量版先验证 harness 的关键边界，再让后续阶段按实际依赖增加复杂度。

## 下一阶段衔接

本阶段解决了：

```text
运行前能解释是否就绪，运行中能观察工具结果和 turn 停止原因。
```

阶段 13 要解决：

```text
agent loop 仍用局部 if/while 决策，尚未显式表达 explore、execute、verify、预算与 widening 策略。
```

本阶段产物会这样支撑下一阶段：

- `turn_stop` 为 kernel 决策结果提供现成的观测出口。
- 稳定日志字段可以继续增加 phase、verification evidence 和 widening 标志。
- readiness 保证进入 kernel 前的基础依赖已经可解释，避免把环境错误误判为 turn policy 问题。
