# MiniCode Lite 架构回顾

本文在 MiniCode Lite 已经跑通端到端闭环之后，重新对照
`D:\JavaProject\MiniCode-Python-main\Docs\Documentation\STRUCTURE.md`，解释两个项目的边界、取舍和演进关系。
目标是建立可复用的架构心智模型，而不是把真实项目的全部模块复制进 Lite。

## 一句话结论

两套代码共享同一条最重要的依赖方向：

```text
entry -> model adapter -> agent loop -> tool registry -> workspace/permissions -> session
```

Lite 把这条链路压缩成可测试的最小闭环；真实 MiniCode-Python 在这条链路周围增加了产品入口、provider 能力、上下文治理、交互界面、记忆和控制论扩展。核心原则是：扩展层可以观察和约束核心路径，但不应让核心路径依赖所有高级能力。

## 1. 分层地图

| 层 | MiniCode Lite | 真实 MiniCode-Python | 架构含义 |
| --- | --- | --- | --- |
| 入口与产品面 | `main.py`、`headless.py`、`repl.py`、`cli_commands.py` | `main.py`、`headless.py`、`tty_app.py`、`manage_cli.py`、TUI | 把用户输入转换为一次 turn 或本地命令 |
| 模型边界 | `types.py`、`mock_model.py`、`qwen_adapter.py`、`model_registry.py` | `types.py`、`mock_model.py`、Anthropic/OpenAI adapter、registry、switcher | loop 只依赖统一的模型步骤，不依赖 provider SDK |
| 编排核心 | `agent_loop.py`、`turn_kernel.py` | 同名模块加 router、task graph、reflection、pipeline | 决定何时问模型、执行工具、验证、停止 |
| 工具与工作区 | `tooling.py`、`tools/`、`workspace.py` | 同名模块加 capability registry 和约 30 个工具 | 工具是受约束的能力，不是任意函数调用 |
| 安全边界 | `permissions.py` | `permissions.py`、`auto_mode.py`、`file_review.py` | 路径、编辑和命令必须在执行前经过边界检查 |
| 持久化 | `session.py`、memory、checkpoint/rewind | `session.py`、history、hooks、background tasks、delta 合并 | 把运行时状态变成可回放、可恢复的证据 |
| 可观测性与交付 | `readiness.py`、`logging_config.py`、`release_gate.py` | readiness、structured logging、release_readiness、product_surfaces | 运行状态和发布证据是独立消费者需要的接口 |
| 高级扩展 | skills、fake MCP、轻量 TUI | MCP stdio、复杂 memory、context compaction、cybernetic | 可选增强，不应成为最小闭环的前置条件 |

## 2. 核心路径逐模块对照

### `agent_loop.py`

Lite 的 loop 只维护消息副本、有限步数和工具生命周期：模型返回 assistant 就交给 kernel 判断终止，返回 tool calls 就记录调用、执行 registry、写回 `tool_result`，然后再次调用模型。这样可以用 `ScriptedModel` 在没有网络的情况下重现 `model -> tool -> model -> final`。

真实项目的 loop 仍是同一控制点，但还承担 provider 不可用时的 fallback、上下文压缩、控制信号、任务链和更丰富的进度事件。它是运行时编排器，不是工具实现仓库。Lite 有意没有复制这些横切策略，避免一次 turn 的教学路径被隐藏状态淹没。

### `turn_kernel.py`

Lite 用 `TurnRecurrentState` 保存 step、phase、空回答重试、verification evidence 和 widening；`decide_assistant_turn`/`decide_tool_turn` 只做策略判断，真实执行仍在 loop。这说明“策略”和“副作用”应分离：策略易测，工具执行有明确边界。

真实 kernel 还包含更丰富的 budget signals、stable task pack、coda summary 和任务图状态。它解决的是大型任务的控制问题，Lite 只保留能证明 phase/verify/stop 契约的部分。

### `tooling.py`

两者都把工具包装成定义、上下文、结果和注册表。Lite 的 `ToolRegistry.execute` 统一做名称查找、输入校验和异常转 `ToolResult(ok=False)`；loop 不需要知道每个工具的异常类型。真实项目在此之上增加 capability、输出裁剪、后台任务和执行日志，因为工具数量和输出规模更大。

### `permissions.py` 与 `workspace.py`

Lite 先把路径解析到 workspace 内，再由 `PermissionManager` 处理外部路径、编辑和危险命令；无交互 headless 默认拒绝需要审批的动作。真实项目将自动模式、提示注入检测、diff 审查继续拆成独立层。共同边界是：权限不是 UI 文案，而是工具真正执行前的安全判定。

### `session.py`

Lite 用一个 JSON 快照保存消息、metadata、checkpoint，并提供 `format_session_replay` 和 rewind。真实项目还支持全量与 delta 合并、历史、hooks 和更丰富的运行时摘要。两者都把 session 当作可验证的状态事实，而不是只保存最终回答；这也是集成测试能检查工具结果、checkpoint 和 replay 的原因。

### `readiness.py`

Lite 的 readiness 是只读、本地、稳定 JSON：检查 Python、workspace、工具数量和 model/mock 模式。缺少 provider 凭据时是 `warning/mock`，不阻断离线学习。真实项目的 readiness 还带诊断、修复计划、模拟 fallback、证据 bundle 和更细的失败等级。Lite 保留了“状态是机器接口”的原则，后续复杂度可以在不改变核心 loop 的情况下增加。

## 3. 产品面与高级优化层

产品面包括本地 slash 命令、headless、REPL、readiness 和 release gate。它们应该调用核心服务，而不是重新实现工具或 session 规则；例如 `/read` 复用 `ToolRegistry`，`/session-replay` 复用 session formatter。

高级层包括真实项目的 provider streaming、MCP stdio、上下文压缩、三层 memory、TUI 渲染和 cybernetic 控制器。这些能力有真实价值，但需要更多运行时状态、外部依赖和故障模型。阶段 17 的结论是先保持它们为扩展点，等有明确消费者和测试证据后再引入。

## 4. 当前 Lite 的核心数据流

```text
用户输入
  -> main/headless/repl
  -> build prompt + create model adapter
  -> agent_loop
       -> turn_kernel 决策
       -> ToolRegistry + ToolContext
            -> workspace 路径边界
            -> permissions 审批
            -> tool 执行
       -> tool_result 回到消息历史
  -> assistant final
  -> session 保存与 replay
  -> readiness/release gate 提供外部证据
```

## 5. 从真实项目迁移的测试思想

- 用 `ScriptedModel` 替代真实 provider，验证模型步骤契约而不是网络稳定性。
- 用 `tmp_path` 隔离 workspace、session、memory 和 checkpoint，避免测试依赖开发者机器状态。
- 用 fake tool 和 permission handler 验证 registry、审批和异常边界。
- 对 provider unavailable、空回答、无工具、路径越界等失败场景断言“可诊断结果”，而不是 traceback。
- 用集成测试验证 `prompt -> tool -> final -> session -> replay` 和 `write -> checkpoint -> rewind`；用 release gate 验证机器输出 schema。

## 6. 暂不复制的内容

暂不复制完整 TUI 渲染、真实 provider streaming、MCP stdio 协议、复杂 context compaction、控制论 PID/自愈、向量记忆和 artifact bundle。这些不是被否定，而是后置到有明确需求、稳定接口和独立测试之后。当前 Lite 的架构边界允许逐项接入，不需要重写 agent loop。

## 7. 架构判断标准

后续新增能力前先回答四个问题：

1. 它属于入口、编排、工具、安全、持久化还是观察层？
2. 它能否通过已有接口接入，而不让 loop 直接依赖 provider/UI 细节？
3. 它是否有离线替身和失败路径测试？
4. 禁用它时，`entry -> agent_loop -> tools -> session` 是否仍能运行？

如果第四个问题答案是否定的，应先重新评估它是不是核心契约，而不是把可选优化偷偷变成必需依赖。

