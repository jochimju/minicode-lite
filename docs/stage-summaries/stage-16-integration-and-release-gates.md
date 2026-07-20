# 阶段 16：集成测试和发布门禁学习总结

## 主题

本阶段把此前分散验证的模型、agent loop、工具、权限、session、checkpoint、rewind、readiness 和 headless 入口连接成可回归的完整链路，并用一个离线发布门禁统一给出“当前版本是否可交付”的结论。

大白话讲：单元测试能证明每个零件大致正常，但不能证明零件装到一起后还能工作。阶段 16 做的是整车试跑，并把每次发版前必须检查的项目固定成一条命令。

## 问题是什么

前 15 个阶段已经有大量单元测试，但跨模块契约仍可能断裂。例如工具结果能单独生成，不代表它一定会进入最终 session；文件写入能成功，不代表 checkpoint 一定先创建；readiness 能生成 Python 对象，不代表命令行真的输出合法 JSON。

发布前如果只依赖人工记忆执行若干命令，也容易漏掉测试或误用本机真实 API 配置。因此需要两层保护：集成测试验证完整数据流，发布门禁固定检查顺序和退出码。

## 解决方案

- 新增 `tests/test_integration.py`，覆盖 `prompt -> tool -> final -> session -> replay`。
- 覆盖 `write -> checkpoint -> rewind`，证明修改和恢复属于同一条真实链路。
- 覆盖 readiness 的机器可读 JSON，以及 Windows 反斜杠路径经过工具和 session 的行为。
- 新增 `minicode_lite/release_gate.py`，依次执行 compile、import、pytest、readiness JSON 和 headless smoke。
- 门禁显式清空 provider 配置、强制使用 mock，并把 smoke session 放入临时目录。
- 新增 `minicode-lite-release` 命令入口，同时支持文本和 JSON 报告。

## 工作原理

### 心智模型

集成测试回答“关键业务路径是否真的连通”，发布门禁回答“所有交付前证据是否同时成立”。前者是测试内容，后者是证据编排器。门禁不重新实现 agent，也不根据日志猜测成功，而是调用真实入口并检查退出码和结构化输出。

### 核心对象

- `ReleaseCheck`：一个稳定命名的检查结果，包含 `pass/fail` 和有限排障摘要。
- `ReleaseReport`：不可变的本次门禁快照；任一检查失败时整体为 `fail`。
- `run_release_gate`：按固定顺序执行五项检查，并对 readiness 和 headless 输出做语义校验。
- `_run_process`：统一子进程边界，不经过 shell，捕获退出码和有限输出。
- `tests/test_integration.py`：使用临时工作区和 scripted model 驱动真实模块协作。

### 当前核心流程

```text
release command
  -> compile package
  -> import public runtime
  -> run complete pytest suite
  -> run /readiness --json -> validate schema and usable status
  -> run offline headless prompt -> validate deterministic final answer
  -> all pass ? exit 0 : exit 1
```

端到端读文件链路：

```text
prompt -> ScriptedModel -> read_file -> tool_result -> assistant final
       -> save_session -> load latest -> format replay
```

恢复链路：

```text
write_file -> permission approval -> checkpoint old content -> write new content
           -> save session -> rewind checkpoint -> restore old content
```

## 对应核心文档

本阶段对照了参考项目 `D:\JavaProject\MiniCode-Python-main` 中的：

- `tests/test_integration.py`：学习用临时工作区、mock model、真实工具和权限替身验证完整消息流。
- `tests/test_integration_rounds.py`：理解跨轮次状态比孤立函数断言更能发现契约断裂。
- `minicode/release_readiness.py`：理解发布检查需要稳定状态、结构化证据、路径规范化和敏感信息保护。
- `minicode/structure_check.py`：理解结构门禁的价值，但当前阶段没有复制完整结构规则。

## 学习产出

- `minicode_lite/release_gate.py`
- `tests/test_integration.py`
- `tests/test_release_gate.py`
- `pyproject.toml` 中的 `minicode-lite-release` 入口
- README 中的发布门禁使用说明
- 本阶段学习总结与面试题库

## 测试验证

执行：

```powershell
python -m pytest -q
python -m minicode_lite.release_gate --json
```

2026-07-20 全量结果为 `178 passed, 1 skipped`。跳过项仍是必须显式启用、可能产生真实网络请求和费用的 live Qwen 测试。

真实发布门禁的 compile、import、pytest、readiness JSON、headless smoke 五项全部为 `pass`，整体退出码为 `0`。readiness 在没有真实模型配置时为 `warning/mock`，这是可用的离线教学状态，不应错误地阻断发布门禁。

## 和真实 MiniCode-Python 的差异

轻量版保留了端到端工具链、session/replay、恢复链路、稳定报告和失败退出码。真实项目的发布 readiness 还包含更细的 `warning/at-risk/blocked` 分级、证据路径规范化、敏感字段与 token 扫描、证据文件和 artifact bundle、更多 provider 与产品表面检查。

本阶段没有复制完整结构检查、live provider smoke、签名制品或跨平台 CI 矩阵。原因是当前目标是建立最小可靠门禁；没有真实发布基础设施时提前复制完整 bundle，只会制造没有消费者的结构和维护成本。

## 常见误区

- 误区：全量单元测试通过就等于集成链路正确。纠正：跨模块消息格式、持久化和恢复顺序仍需端到端测试。
- 误区：readiness 出现 warning 就必须失败。纠正：本项目的 mock fallback 是明确支持的离线模式，blocked 才表示基础条件不可用。
- 误区：发布 smoke 应调用真实模型。纠正：默认门禁必须确定、离线、免费；live 测试应显式启用并单独管理。
- 误区：门禁只要运行命令，不必解析输出。纠正：退出码为 0 仍可能输出错误 schema 或意外回答，因此关键机器接口要做语义校验。
- 误区：集成测试可直接使用开发者真实 session 目录。纠正：测试和 smoke 必须隔离状态，避免污染数据和产生顺序依赖。

## 复习提示

重点复习三件事：为什么集成测试仍要使用真实工具而只替换模型；为什么发布门禁同时检查退出码和输出语义；为什么 mock-ready 是可发布的教学模式，而真实 provider 连通性属于显式 live gate。

自测问题：如果 pytest 通过但 readiness 输出不再是合法 JSON，门禁应如何表现？如果 write 成功但 checkpoint 未保存，哪条集成测试会发现？为什么 Windows 反斜杠路径需要单独覆盖？

## 下一阶段衔接

阶段 17 将以这套测试和门禁为稳定基线，对照真实 MiniCode-Python 写架构回顾。架构笔记可以区分核心路径、产品面和高级优化层，而无需担心回顾过程中悄悄破坏当前行为。

## 面试高频问题与参考答案

### 1. 单元测试和集成测试在 harness 中分别解决什么问题？

**参考答案：** 单元测试验证单个对象的局部契约，例如 validator 是否拒绝错误输入；集成测试验证多个真实模块连接后的数据流，例如模型发出 tool call 后，结果是否进入下一次模型调用、session 和 replay。两者不能互相替代：集成测试定位较慢，单元测试又看不到跨边界错误。

### 2. 阶段 16 的读文件端到端链路经过哪些核心对象？

**参考答案：** 用户 prompt 进入 headless，scripted model 返回 `read_file` 调用，`ToolRegistry` 用带 cwd、权限和 session 的 `ToolContext` 执行工具，结果写回消息历史；模型再给 final，headless 保存完整 session，最后 replay 从持久化消息派生可读时间线。测试断言工具结果和最终回答都真实存在。

### 3. 为什么发布门禁要强制使用 mock model？

**参考答案：** 默认门禁必须确定、可重复、离线且无费用。真实 provider 会受网络、额度、服务状态和模型行为变化影响，容易造成非代码原因的随机失败。live smoke 仍有价值，但应作为显式启用的独立检查，不能替代默认回归门禁。

### 4. readiness 为 `warning/mock` 时为什么门禁仍可通过？

**参考答案：** 本项目明确把 mock fallback 作为学习和测试的可用运行模式，因此缺少 Qwen 凭据不是基础功能阻断。门禁要求 readiness schema 合法且状态为 `ready` 或 `warning`；如果 Python、工作区或工具不可用而状态为 `blocked`，才应该失败。

### 5. 为什么只检查子进程退出码还不够？

**参考答案：** 退出码只能说明程序自认为成功，不能证明输出满足消费者契约。例如 readiness 可能因回归输出普通文本，headless 可能返回意外占位符，但进程仍为 0。因此门禁还解析 JSON schema，并核对 mock smoke 的确定性最终回答。

### 6. 场景题：write_file 已写入新内容，但 rewind 无法恢复，如何排查？

**参考答案：** 先检查工具执行时是否传入同一个 session，再检查权限批准之后、真正写盘之前是否调用 checkpoint，随后确认 session 是否保存了 checkpoint。最后运行 `write -> checkpoint -> rewind` 集成测试定位断点。不能只看 write 的成功文本，因为恢复能力依赖写入前的状态证据。

### 7. 取舍题：为什么不一次复制真实 MiniCode 的完整 release artifact bundle？

**参考答案：** 当前项目只有单一轻量运行时，核心需求是让关键链路可重复验证。完整 bundle 还需要证据清单、脱敏扫描、多级风险状态、结构规则和制品消费者；提前复制会增加空结构和维护负担。先稳定五项最小门禁，等真实发布需求出现再按证据扩展，更符合渐进式 harness 学习目标。

### 8. Windows 路径测试能发现什么普通测试不容易发现的问题？

**参考答案：** Windows 使用盘符、反斜杠和大小写不敏感语义。只用 POSIX 风格路径可能漏掉反斜杠被当成普通字符、`commonpath` 跨盘异常、session 中路径表示变化等问题。本阶段让反斜杠路径真实经过工具执行和 session 保存，验证的不只是字符串函数。

### 9. 如何避免发布门禁污染开发者环境？

**参考答案：** 门禁不经过 shell，显式清空真实 provider 配置，把 session 目录指向临时目录，并让测试使用 `tmp_path`。这样不会联网、不会消费配额、不会写入真实 session，也不会依赖上一次运行残留的状态。临时目录在门禁结束后自动清理。

### 10. 发布门禁失败时应该优先看什么？

**参考答案：** 先看失败检查的稳定名称，再看有限输出。compile/import 失败通常是语法或包结构问题；pytest 失败看首个断言；readiness 失败检查 schema 和 blocked 项；headless smoke 失败检查模型选择、入口路由和最终回答。按检查边界定位比重跑整套流程后猜测更有效。
