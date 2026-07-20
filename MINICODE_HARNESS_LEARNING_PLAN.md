# MiniCode Harness 从 0 搭建学习计划

本计划用于在当前 `minicode-lite` 项目中，从零实现一个轻量版 MiniCode，目标不是复制完整产品，而是理解 MiniCode Python 的 harness 工程：入口、模型-工具循环、工具注册、权限边界、会话持久化、检查点、回放、测试夹具和可观测性。

参考项目：

- `D:\JavaProject\MiniCode-Python-main`

参考项目核心路径：

- 入口：`minicode/main.py`、`minicode/headless.py`
- 循环：`minicode/agent_loop.py`、`minicode/turn_kernel.py`
- 类型：`minicode/types.py`
- 模型：`minicode/mock_model.py`、`minicode/model_registry.py`
- 工具：`minicode/tooling.py`、`minicode/tools/`
- 权限：`minicode/permissions.py`、`minicode/workspace.py`
- 会话：`minicode/session.py`、`minicode/history.py`
- 产品面：`minicode/cli_commands.py`、`minicode/readiness.py`、`minicode/product_surfaces.py`
- 测试：`tests/test_agent_loop.py`、`tests/test_tools.py`、`tests/test_session.py`、`tests/test_headless.py`
- 结构说明：`Docs/Documentation/STRUCTURE.md`

## 三条学习原则

每个阶段都必须遵循同一套节奏：

1. 先跑通最小闭环：先让一条用户输入穿过最短路径并得到可观察输出。
2. 对照 MiniCode-Python 真实模块理解：只选本阶段相关模块阅读，记录差异，不一次性吞全量架构。
3. 写测试验证：每个阶段必须有 pytest 用例，优先用 `tmp_path`、脚本化模型、假工具、假配置验证行为。

## 当前仓库起步状态

当前 `D:\JavaProject\minicode-lite` 基本为空，只看到一个 `.git` 目录，但本地 `git status` 未识别为有效 Git 仓库。第一阶段开始前需要修复或重新初始化 Git。

建议先执行：

```powershell
git init
git status
```

如果要同时推送 GitHub 和 Gitee：

```powershell
git remote add github <your-github-repo-url>
git remote add gitee <your-gitee-repo-url>
git remote -v
```

如果只使用一个远端，也可以用传统的 `origin`：

```powershell
git remote add origin <your-repo-url>
```

## 每阶段固定收尾

每个阶段完成后都必须先生成一份学习总结文档，再执行检查和上传流程。

阶段总结文档存放在：

```text
docs/stage-summaries/stage-XX-<阶段主题>.md
```

阶段总结必须面向后续复习，至少包含这些内容：

- 主题：这一阶段学习的主线是什么。
- 问题是什么：为什么需要做这个阶段，它解决 harness 中哪个具体问题。
- 解决方案：本阶段采用了什么最小实现方案。
- 工作原理：核心流程、关键对象、数据如何流动。
- 对应核心文档：参考项目中本阶段对照阅读了哪些真实模块、测试或文档。
- 学习产出：新增代码、测试、命令、文档、能力边界。
- 测试验证：执行了哪些测试，验证了哪些行为。
- 和真实 MiniCode-Python 的差异：哪些保留、哪些简化、哪些后置。
- 复习提示：下次复习时最应该重新理解的问题。
- 下一阶段衔接：本阶段产物如何支撑下一阶段。

可以直接复制模板：

- `docs/stage-summaries/STAGE_SUMMARY_TEMPLATE.md`

完成总结后执行：

```powershell
python -m pytest -q
git status --short
git add .
git commit -m "stage-XX: <阶段名称>"
git tag stage-XX
git push github main --tags
git push gitee main --tags
```

如果只配置了 `origin`：

```powershell
git push origin main --tags
```

注意：

- 测试失败不要提交。
- `.env`、API key、真实 session 数据、临时输出不要提交。
- 每个阶段提交前必须补齐对应的学习总结文档。
- 每个阶段提交前更新本计划中的阶段状态，或者新增一条学习日志。

## 建议目录结构

先保持小而清楚，后面按阶段扩展：

```text
minicode-lite/
  pyproject.toml
  README.md
  AGENTS.md
  MINICODE_HARNESS_LEARNING_PLAN.md
  docs/
    stage-summaries/
      STAGE_SUMMARY_TEMPLATE.md
      stage-00-scaffold.md
  minicode_lite/
    __init__.py
    types.py
    mock_model.py
    config.py
    prompt.py
    model_registry.py
    qwen_adapter.py
    tooling.py
    agent_loop.py
    turn_kernel.py
    workspace.py
    permissions.py
    headless.py
    main.py
    tools/
      __init__.py
      list_files.py
      read_file.py
      write_file.py
      edit_file.py
      patch_file.py
      run_command.py
  tests/
    test_types.py
    test_mock_model.py
    test_tooling.py
    test_agent_loop.py
    test_tools.py
    test_headless.py
```

## 粗粒度学习路线图：先看全局，再进入 0–17 阶段

下面的 0–17 阶段是可以逐个动手、逐个测试的细粒度清单；下面 6 个大阶段则是一张用于学习、复盘和定位当前进度的路线图。学习时建议先看这张图，知道当前代码在整个 harness 里的位置；实施时再回到对应的细粒度阶段完成最小闭环。

```text
基础闭环（0–3）
  -> 本地工作代理（4–5）
  -> 真实运行时与安全边界（6–7）
  -> 状态、恢复与记忆（8–10）
  -> 控制面与运行时治理（11–13）
  -> 扩展、交互、发布与架构回顾（14–17）
```

| 大阶段 | 对应细粒度阶段 | 这一段的核心问题 | 阶段完成后获得的能力 |
| --- | --- | --- | --- |
| 1. Harness 基础与最小闭环 | 0–3 | 一个 agent 的最短可测试链路如何成立？ | 离线跑通 `model -> tool -> model -> final` |
| 2. 本地工作代理 | 4–5 | agent 怎样安全地接触当前项目，并从命令行被使用？ | 文件工具、工作区边界、CLI/headless 单轮入口 |
| 3. 真实运行时与安全边界 | 6–7 | 怎样接入真实模型，同时把危险动作限制在明确边界内？ | Qwen/OpenAI-compatible 调用、mock 后备、权限审批 |
| 4. 状态、恢复与记忆 | 8–10 | 多轮工作怎样保存、回放、恢复并记住关键信息？ | session、checkpoint、rewind、最小 memory |
| 5. 控制面与运行时治理 | 11–13 | 用户怎样控制 agent，开发者怎样观察和校验每个 turn？ | 本地命令、readiness/日志、turn kernel 策略 |
| 6. 扩展、交互、发布与架构回顾 | 14–17 | 怎样让系统可扩展、可交互、可回归验证，并形成架构理解？ | skills、REPL/TUI、集成门禁、架构笔记 |

### 大阶段 1：Harness 基础与最小闭环（细粒度阶段 0–3）

**核心要实现什么：** 建好可安装、可测试、可提交的项目骨架；定义模型消息、工具调用、工具结果等共享类型；先用可预测的 mock/scripted model 替代真实 API；再用工具注册表和最小 agent loop 把一次工具调用闭环跑通。

**完成标志：** 不联网也能通过测试复现 `用户输入 -> 模型请求工具 -> 执行工具 -> 模型给出最终回答`。这说明 harness 的骨架、数据契约和控制循环已经成立。

**下一大阶段要做什么：** 把“内存中的假工具”换成真正面向当前项目的工作能力，并让用户能从命令行启动它。

### 大阶段 2：本地工作代理（细粒度阶段 4–5）

**核心要实现什么：** 引入 workspace，把文件访问限制在项目根目录内；实现列目录、读文件、写文件、编辑文件等工具；提供 CLI 和 headless 入口，把用户的单轮自然语言请求送进 agent loop。

**完成标志：** agent 能通过受 workspace 约束的文件工具操作当前项目，用户也能在终端运行一条单轮任务；测试能覆盖正常路径和越界路径。

**下一大阶段要做什么：** 用真实 Qwen/OpenAI-compatible 模型替换 scripted model 的演示角色，同时保留 mock 后备，避免测试依赖网络和密钥。

### 大阶段 3：真实运行时与安全边界（细粒度阶段 6–7）

**核心要实现什么：** 配置加载、prompt 组织、模型注册和 Qwen adapter，让 CLI 可以读取 `.env` 并调用真实模型；接着为文件修改和命令执行建立权限、路径检查和审批边界。

**完成标志：** 配置真实 API Key 时能完成一次可观察的真实模型调用；未配置时仍能给出明确诊断或使用测试用 mock。危险的文件/命令动作不能绕过权限策略。当前进度为阶段 0–6 已完成，下一细粒度任务是阶段 7“权限和命令执行”。

**下一大阶段要做什么：** 让一次次独立的运行变成可持续的工作过程：保存历史、留下恢复点，并沉淀可检索的项目记忆。

### 大阶段 4：状态、恢复与记忆（细粒度阶段 8–10）

**核心要实现什么：** 持久化 session 并支持 replay；在改文件前建立 checkpoint、必要时 rewind；再实现一个小而可验证的 memory，把重要事实写入、检索并注入后续请求。

**完成标志：** 一次工作可以被保存和回放，错误修改可恢复，后续任务能检索到先前显式写入的关键信息。

**下一大阶段要做什么：** 把这些内部能力变成用户可操作、开发者可观察的运行时控制面。

### 大阶段 5：控制面与运行时治理（细粒度阶段 11–13）

**核心要实现什么：** 增加 `/session`、`/memory`、`/rewind` 等本地产品命令；输出 readiness 和日志；抽出 turn kernel，明确一个 turn 的 phase、验证和必要时 widening 策略。

**完成标志：** 用户能管理会话、记忆和恢复点；开发者能看见系统是否准备就绪、每轮如何推进；模型循环不再是黑盒 `while`，而是有状态、有策略的调度过程。

**下一大阶段要做什么：** 在稳定的运行时之上扩展 skills 和交互界面，并用发布级测试与架构笔记收束学习成果。

### 大阶段 6：扩展、交互、发布与架构回顾（细粒度阶段 14–17）

**核心要实现什么：** 发现并加载本地 skills；提供轻量 REPL/TUI；建立端到端 smoke、集成测试和 release checklist；最后对照真实 MiniCode-Python 写出架构回顾。

**完成标志：** 项目既能扩展也能交互使用，核心链路有回归保护；你能从入口、模型、循环、工具、权限、状态到产品面讲清这套 harness 的设计取舍。

**下一大阶段要做什么：** 路线完成后不急着堆功能。以架构笔记和测试为基线，选择一个真实需求做小范围增强，并始终维持“最小闭环、对照真实模块、测试验证”的节奏。

## 细粒度实施阶段（0–17）

## 阶段 0：项目脚手架和 Git 基线

目标：让空项目变成一个可以安装、可以测试、可以提交的 Python 项目。

### 先跑通最小闭环

- 创建 `pyproject.toml`，项目名建议 `minicode-lite`。
- 创建 `minicode_lite/__init__.py`。
- 创建一个最小 CLI：运行后输出 `MiniCode Lite ready`。
- 创建 `tests/test_smoke.py`，验证包可导入，CLI 主函数可调用。

### 对照真实模块理解

- 阅读 `MiniCode-Python-main/pyproject.toml`，理解 console scripts。
- 阅读 `minicode/main.py`，只关注入口职责，不追深层依赖。
- 阅读 `Docs/Documentation/STRUCTURE.md` 的“入口与运行时”部分。

### 写测试验证

- `python -m pytest -q`
- 至少验证：
  - `import minicode_lite` 成功。
  - CLI 函数返回或打印固定内容。

### Git 上传

- 提交信息：`stage-00: scaffold python project`
- 标签：`stage-00`
- 推送 GitHub/Gitee。

## 阶段 1：核心类型和脚本化模型

目标：先不接真实大模型，用可控的 scripted/mock model 建立测试 harness。

### 先跑通最小闭环

- 实现 `types.py`：
  - `ChatMessage`
  - `ToolCall`
  - `AgentStep`
  - `StepDiagnostics`
  - `ModelAdapter`
- 实现 `mock_model.py`：
  - `ScriptedModel`：按预设步骤返回。
  - `MockModelAdapter`：根据简单输入返回固定助手消息或工具调用。

### 对照真实模块理解

- 对照 `minicode/types.py`，理解 `assistant` 和 `tool_calls` 两类 `AgentStep`。
- 对照 `minicode/mock_model.py`，理解为什么测试不直接依赖真实 provider。
- 重点记录：真实项目将模型输出抽象为 `AgentStep`，agent loop 不关心 provider 细节。

### 写测试验证

- `test_types.py`：构造消息、工具调用、诊断对象。
- `test_mock_model.py`：
  - 无工具时返回 assistant。
  - 输入 `/read demo.txt` 时返回 `read_file` 工具调用。
  - 脚本化模型按顺序返回步骤。

### Git 上传

- 提交信息：`stage-01: add core types and mock model`
- 标签：`stage-01`
- 推送 GitHub/Gitee。

## 阶段 2：工具注册表和第一个工具闭环

目标：实现工具 harness，让工具可以注册、查找、校验、执行、返回结构化结果。

### 先跑通最小闭环

- 实现 `tooling.py`：
  - `ToolResult`
  - `ToolContext`
  - `ToolDefinition`
  - `ToolRegistry`
- 先实现一个测试用 `echo` 工具。
- 能完成：模型发起 `echo` 工具调用，registry 执行，返回 `ToolResult`。

### 对照真实模块理解

- 对照 `minicode/tooling.py`。
- 只学习这些机制：
  - 工具名索引。
  - 输入校验。
  - 未知工具返回错误而不是崩溃。
  - 工具异常转换成 `ToolResult(ok=False)`。
  - 大输出截断可以先不实现。

### 写测试验证

- `test_tooling.py`：
  - 能注册并执行工具。
  - 未知工具返回错误。
  - validator 抛错会变成错误结果。
  - run 抛错不会让整个测试崩溃。

### Git 上传

- 提交信息：`stage-02: add tool registry harness`
- 标签：`stage-02`
- 推送 GitHub/Gitee。

## 阶段 3：最小 agent loop

目标：实现 MiniCode harness 的心脏：用户消息 -> 模型 -> 工具 -> 模型 -> 最终回答。

### 先跑通最小闭环

- 实现 `agent_loop.py` 的 `run_agent_turn`。
- 支持：
  - assistant final 直接结束。
  - tool_calls 写入 `assistant_tool_call`。
  - 执行工具后写入 `tool_result`。
  - 再次调用模型直到最终 assistant。
  - `max_steps` 防止死循环。
- 暂时不实现复杂控制论、压缩、memory、TUI。

### 对照真实模块理解

- 对照 `minicode/agent_loop.py`，只看基础循环和 `_execute_single_tool` 相关路径。
- 对照 `tests/test_agent_loop.py`，学习用 `ScriptedModel` 驱动 loop。
- 对照 `minicode/turn_kernel.py`，只理解为什么真实项目把 step、phase、verification 拆出去。

### 写测试验证

- `test_agent_loop.py`：
  - 工具调用后能得到最终 assistant。
  - 工具结果进入 messages。
  - 空 assistant 响应可以重试一次。
  - 超过 max_steps 返回错误或停止原因。
  - 回调 `on_tool_start`、`on_tool_result`、`on_assistant_message` 可被触发。

### Git 上传

- 提交信息：`stage-03: implement minimal agent loop`
- 标签：`stage-03`
- 推送 GitHub/Gitee。

## 阶段 4：工作区边界和文件工具

目标：让 agent 能安全地读写当前项目文件，同时理解 MiniCode 的本地优先设计。

### 先跑通最小闭环

- 实现 `workspace.py`：
  - `resolve_tool_path(context, path, mode)`
  - 默认只允许访问 cwd 内文件。
- 实现基础文件工具：
  - `list_files`
  - `read_file`
  - `write_file`
  - `edit_file`
  - `patch_file`
- 工具路径统一走 `resolve_tool_path`。

### 对照真实模块理解

- 对照 `minicode/workspace.py`。
- 对照 `minicode/tools/read_file.py`、`write_file.py`、`edit_file.py`、`patch_file.py`、`list_files.py`。
- 对照 `tests/test_tools.py` 中 `tmp_path` 的写法。
- 重点理解：工具是 agent 的手，workspace boundary 是护栏。

### 写测试验证

- `test_tools.py`：
  - 读取 UTF-8 文本。
  - 写入新文件。
  - 替换文件中的一段文本。
  - patch 多段替换。
  - `../outside.txt` 这种路径默认拒绝。
  - 二进制文件读取给出友好错误。

### Git 上传

- 提交信息：`stage-04: add workspace and file tools`
- 标签：`stage-04`
- 推送 GitHub/Gitee。

## 阶段 5：CLI 和 headless 单轮模式

目标：把库变成可以从命令行运行的工具，先跑通非交互 headless。

### 先跑通最小闭环

- 实现 `headless.py`：
  - 接收 prompt。
  - 初始化 mock model、默认工具、messages。
  - 调用 `run_agent_turn`。
  - 打印最后一条 assistant。
- 实现 `main.py`：
  - 支持 `python -m minicode_lite "hello"`。
  - 支持基本 slash command，如 `/tools`、`/read <path>`。
- 在 `pyproject.toml` 配置 console scripts：
  - `minicode-lite`
  - `minicode-lite-headless`

### 对照真实模块理解

- 对照 `minicode/headless.py`，理解非交互 CI 模式为什么重要。
- 对照 `minicode/main.py`，只关注：
  - 参数解析。
  - 初始化 tools/model/permissions。
  - 本地命令和 agent turn 的分流。
- 对照 `minicode/local_tool_shortcuts.py`，理解 slash command 到工具调用的转换。

### 写测试验证

- `test_headless.py`：
  - prompt 为空时失败。
  - 普通 prompt 返回 mock assistant。
  - `/read demo.txt` 能读到文件内容。
- CLI 测试可以用 subprocess，也可以先直接调用函数。

### Git 上传

- 提交信息：`stage-05: add cli and headless mode`
- 标签：`stage-05`
- 推送 GitHub/Gitee。

## 阶段 6：prompt、配置和模型注册

目标：把 mock harness 升级成可配置 runtime，提前接入真实 Qwen/OpenAI-compatible 模型，但仍保持 mock 为默认安全后备。

### 先跑通最小闭环

- 实现 `config.py`：
  - 从环境变量读取模型名、API key、base URL。
  - 支持一个本地 settings JSON。
  - 缺配置时返回 mock runtime 或明确诊断。
- 实现 `prompt.py`：
  - 构建 system prompt。
  - 注入 cwd、工具列表、权限摘要占位、memory 占位。
- 实现 `model_registry.py`：
  - `create_model_adapter`
  - 默认返回 `MockModelAdapter`。
  - 配置完整时返回真实模型 adapter。
- 实现最小 Qwen/OpenAI-compatible adapter：
  - 支持阿里云百炼/DashScope OpenAI 兼容接口。
  - 先跑通普通 chat completion。
  - tool calling 只做本项目当前工具协议需要的最小映射。

### 对照真实模块理解

- 对照 `minicode/config.py`，理解配置优先级。
- 对照 `minicode/prompt.py`，理解系统提示由静态规则和动态运行时信息组成。
- 对照 `minicode/model_registry.py`，理解 provider 适配和 fallback 的边界。
- 对照真实 provider adapter 时，只学习“本项目消息格式如何映射到 provider API”，暂不复制 streaming 和复杂 fallback 链。

### 写测试验证

- 环境变量优先级。
- settings 文件可加载。
- 缺配置时不崩溃，并回退到 mock。
- prompt 包含 cwd、工具名、权限摘要占位。
- `create_model_adapter` 默认可返回 mock。
- 配置 Qwen/DashScope 时能构造真实 adapter。
- 用 fake HTTP/client 验证 adapter 会发送正确的 model、messages 和 tools 结构。

### Git 上传

- 提交信息：`stage-06: add prompt config and qwen model adapter`
- 标签：`stage-06`
- 推送 GitHub/Gitee。

### 完成状态（已完成）

阶段 06 的实现、离线测试、opt-in live Qwen 测试和学习总结已补齐。2026-07-13 的本次全量测试结果为 `71 passed, 1 skipped`；通过临时设置 `MINICODE_LITE_LIVE_QWEN_TEST=1` 运行的 live marker 测试为 `1 passed`，已完成真实 DashScope endpoint 连通性验证。

- 学习总结：[stage-06-prompt-config-qwen-model-adapter.md](docs/stage-summaries/stage-06-prompt-config-qwen-model-adapter.md)

## 阶段 7：权限管理和命令执行

目标：实现最小可用的权限 harness，避免 agent 任意执行危险操作。

### 先跑通最小闭环

- 实现 `permissions.py`：
  - `PermissionManager`
  - 路径读写检查。
  - 命令执行检查。
  - 编辑审批检查。
  - 测试中可注入 prompt handler。
- 实现 `run_command` 工具：
  - 只读命令默认放行。
  - 写入/危险命令需要 permission prompt。
  - 超时和输出截断。

### 对照真实模块理解

- 对照 `minicode/permissions.py`：
  - 路径归一化。
  - Windows 大小写处理。
  - `allow_once`、`deny_once`、turn-level approval。
- 对照 `minicode/tools/run_command.py`：
  - Windows shell builtin 处理。
  - `rm -rf`、管道下载执行等危险片段识别。
- 不要急着复制 `auto_mode.py` 全量逻辑。

### 写测试验证

- `test_permissions.py`：
  - cwd 内读允许。
  - cwd 外写拒绝。
  - prompt handler allow 后通过。
- `test_tools.py`：
  - `echo hello` 成功。
  - 危险命令被 prompt 拦截。
  - prompt deny 时不会执行命令。

### Git 上传

- 提交信息：`stage-07: add permissions and command tool`
- 标签：`stage-07`
- 推送 GitHub/Gitee。

### 完成状态（已完成）

阶段 07 的权限管理、编辑审批、命令执行工具、turn 级授权生命周期和学习总结已补齐。2026-07-17 的本次全量测试结果为 `88 passed, 1 skipped`；跳过项仍是需要显式启用的 live Qwen 测试。危险命令、下载后执行片段、编辑拒绝、命令超时和大输出截断均有离线测试验证。

- 学习总结：[stage-07-permissions-and-command-execution.md](docs/stage-summaries/stage-07-permissions-and-command-execution.md)

## 阶段 8：session 持久化和 replay

目标：让一次 agent turn 不再只是内存里的临时过程，而是可检查、可回放的运行记录。

### 先跑通最小闭环

- 实现 `session.py`：
  - `SessionData`
  - `SessionMetadata`
  - `create_new_session`
  - `save_session`
  - `load_session`
  - `list_sessions`
  - `get_latest_session`
  - `format_session_inspect`
  - `format_session_replay`
- headless 或 main 在每轮结束保存 messages 和 transcript。

### 对照真实模块理解

- 对照 `minicode/session.py`，先做全量 JSON 保存，不做 delta 优化。
- 对照 `tests/test_session.py`，学习 session 测试如何 patch session 目录。
- 对照 `minicode/tui/transcript.py`，只借鉴 transcript 的数据形状，不实现完整 TUI。

### 写测试验证

- `test_session.py`：
  - 创建 session。
  - 保存和加载。
  - 按 workspace 过滤。
  - 获取 latest。
  - replay 格式包含 user、assistant、tool_result。

### Git 上传

- 提交信息：`stage-08: add durable sessions and replay`
- 标签：`stage-08`
- 推送 GitHub/Gitee。

### 完成状态（已完成）

阶段 08 已实现全量 JSON session、workspace 过滤、latest、inspect/replay，以及 headless/main 模型轮次结束后的 messages 与 transcript 自动保存。实现保留了真实 MiniCode-Python 的核心状态边界，并按学习目标后置 delta、checkpoint、resume 命令和完整 TUI transcript 生命周期。2026-07-18 的全量测试结果为 `98 passed, 1 skipped`，跳过项仍是需要显式启用的 live Qwen 测试。

- 学习总结：[`stage-08-session-persistence-and-replay.md`](docs/stage-summaries/stage-08-session-persistence-and-replay.md)

## 阶段 9：checkpoint 和 rewind

目标：理解 MiniCode 的恢复优先设计：文件修改前先留快照，出错后能预览和回退。

### 先跑通最小闭环

- 在 `write_file`、`edit_file`、`patch_file` 中：
  - 修改前创建 `FileCheckpoint`。
  - 记录文件路径、是否存在、旧内容、group id。
- 实现：
  - `format_rewind_preview`
  - `rewind_session`
  - `format_session_checkpoints`

### 对照真实模块理解

- 对照 `minicode/session.py` 的 `FileCheckpoint`、`rewind_session_data`、`rewind_session`。
- 对照 `minicode/file_review.py`，理解“写前审查 + checkpoint”在真实项目中如何组合。
- 对照 `tests/test_tools.py` 中 checkpoint 测试。

### 写测试验证

- 写已有文件会记录旧内容。
- 写新文件 rewind 后应删除该文件。
- 多次编辑可以按 step 回退。
- preview 不修改磁盘。
- rewind 后 session metadata 的 checkpoint 数量正确。

### Git 上传

- 提交信息：`stage-09: add checkpoints and rewind`
- 标签：`stage-09`
- 推送 GitHub/Gitee。

### 完成状态（已完成）

阶段 09 已实现文件工具写入前 checkpoint、session 全量 JSON 持久化、按 steps 或 checkpoint ID 选择恢复点、纯预览、checkpoint 列表和带反向安全快照的 rewind。恢复前会整批验证路径仍位于 session workspace 内且目标不是目录，避免被篡改的持久数据越界或多文件恢复只完成一半。2026-07-19 的全量测试结果见本阶段学习总结。

- 学习总结：[`stage-09-checkpoint-and-rewind.md`](docs/stage-summaries/stage-09-checkpoint-and-rewind.md)

## 阶段 10：最小 memory 系统

目标：实现轻量记忆闭环：写入项目知识，下一轮 prompt 能检索并注入相关内容。

### 先跑通最小闭环

- 实现 `memory.py`：
  - `MemoryEntry`
  - `MemoryManager`
  - 添加记忆。
  - 简单关键词检索。
  - 保存到 `.mini-code-memory/` 或 `.minicode-lite-memory/`。
- 在 prompt 构建时注入 `memory_context`。

### 对照真实模块理解

- 对照 `minicode/memory.py`，只学习三层 memory 思路，不实现完整 BM25/TF-IDF。
- 对照 `minicode/working_memory.py`，理解 working memory 和 project memory 的差别。
- 对照 `minicode/memory_pipeline.py`，把它视为后续增强，不在本阶段实现。

### 写测试验证

- 添加 memory 后能持久化。
- 查询关键词能返回相关 memory。
- 非字符串内容会被转成字符串或被拒绝。
- prompt 中出现 memory context。

### Git 上传

- 提交信息：`stage-10: add minimal project memory`
- 标签：`stage-10`
- 推送 GitHub/Gitee。

### 完成状态（已完成）

阶段 10 已实现项目级 `MemoryEntry`、`MemoryManager`、原子 JSON 持久化、中英文关键词检索和 headless prompt 注入。memory 与 workspace 绑定，非字符串内容会稳定转换，空内容会被拒绝，损坏文件会安全降级为空记忆。2026-07-20 的全量测试结果为 `121 passed, 1 skipped`，跳过项仍是需要显式启用的 live Qwen 测试。

- 学习总结：[`stage-10-minimal-project-memory.md`](docs/stage-summaries/stage-10-minimal-project-memory.md)

## 阶段 11：本地产品命令

目标：把内部能力包装成用户能操作的本地命令。

### 先跑通最小闭环

- 实现 `cli_commands.py`：
  - `/tools`
  - `/session`
  - `/sessions`
  - `/session-replay`
  - `/checkpoints`
  - `/rewind-preview`
  - `/rewind`
  - `/memory`
- main/headless 能分辨本地命令和普通用户任务。

### 对照真实模块理解

- 对照 `minicode/cli_commands.py`。
- 对照 `minicode/main.py` 中 `_handle_local_command`。
- 对照 README 中 Everyday Commands。

### 写测试验证

- 每个 slash command 都有纯函数测试。
- 没有 session 时返回友好提示。
- rewind-preview 不改文件。
- `/memory` 能显示 memory 状态。

### Git 上传

- 提交信息：`stage-11: add local product commands`
- 标签：`stage-11`
- 推送 GitHub/Gitee。

### 完成状态（已完成）

阶段 11 已实现统一 `cli_commands.py`，支持 `/tools`、`/session`、`/sessions`、`/session-replay`、`/checkpoints`、`/rewind-preview`、`/rewind` 和 `/memory`，并保留阶段 5 的 `/read` 兼容入口。本地命令在 runtime config 和 model adapter 之前执行；session 选择支持 active/latest/显式 ID 且受 workspace 隔离；preview 保持零副作用，rewind 继续保留反向 checkpoint。2026-07-20 的全量测试结果为 `134 passed, 1 skipped`，跳过项仍是需要显式启用的 live Qwen 测试。

- 学习总结：[`stage-11-local-product-commands.md`](docs/stage-summaries/stage-11-local-product-commands.md)

## 阶段 12：readiness 和可观测性

目标：让运行时能回答“我现在是否准备好工作，哪里还缺东西”。

### 先跑通最小闭环

- 实现 `readiness.py`：
  - 检查 Python 版本。
  - 检查 cwd。
  - 检查工具注册。
  - 检查模型配置或 mock fallback。
  - 输出文本和 JSON。
- 实现基础 logging：
  - 工具执行日志。
  - agent turn stop reason。

### 对照真实模块理解

- 对照 `minicode/readiness.py`。
- 对照 `minicode/product_surfaces.py`。
- 对照 `minicode/logging_config.py`。
- 对照 `benchmarks/release_readiness.py`，理解 release gate 但暂不复制。

### 写测试验证

- readiness JSON schema 稳定。
- 缺模型时状态为 warning 或 mock-ready，而不是崩溃。
- 工具为空时能报告 blocked。
- 日志函数可调用。

### Git 上传

- 提交信息：`stage-12: add readiness and observability`
- 标签：`stage-12`
- 推送 GitHub/Gitee。

阶段 12 已实现 `readiness.py` 和最小 `logging_config.py`：`/readiness` 与 `/readiness --json` 会在模型创建前只读检查 Python、cwd、默认工具和 Qwen/mock 模型路径，使用 `ready`、`warning`、`blocked` 三级状态并输出版本化 JSON；`ToolRegistry.execute` 统一记录工具名、成功状态和耗时，agent loop 记录 final、空响应、异常 step 与 max steps 的停止原因，且日志不包含工具输入输出或凭据。2026-07-20 的全量测试结果为 `147 passed, 1 skipped`，跳过项仍是需要显式启用的 live Qwen 测试。

- 学习总结：[`stage-12-readiness-and-observability.md`](docs/stage-summaries/stage-12-readiness-and-observability.md)

## 阶段 13：turn kernel 的 phase、widening、verification

目标：把最小 loop 拆成更容易推理和测试的 turn policy，理解真实 MiniCode 的 harness 控制点。

### 先跑通最小闭环

- 实现 `turn_kernel.py`：
  - `TurnRecurrentState`
  - `TurnStepPolicy`
  - `derive_turn_step_policy`
  - `decide_assistant_turn`
  - `decide_tool_turn`
- 支持：
  - explore -> execute -> verify。
  - max steps。
  - 空响应 retry。
  - verification evidence 不足时阻止过早 final。
  - 简单 widening：接近 step 上限时增加一次预算。

### 对照真实模块理解

- 对照 `minicode/turn_kernel.py`。
- 对照 `tests/test_turn_kernel.py`。
- 回头整理 `agent_loop.py`，把策略判断从 loop 中挪到 kernel。

### 写测试验证

- phase transition。
- max steps 命中。
- empty response retry。
- verification evidence 缺失时进入 guard。
- widening 只触发一次。

### Git 上传

- 提交信息：`stage-13: add turn kernel policies`
- 标签：`stage-13`
- 推送 GitHub/Gitee。

### 完成状态（已完成）

阶段 13 已实现轻量 `turn_kernel.py`：用 `TurnRecurrentState` 集中维护步数、phase、空响应重试、工具观察、verification evidence、widening 与停止原因；用 `TurnStepPolicy` 和 `derive_turn_step_policy` 显式表达 `explore -> execute -> verify`；用 `decide_assistant_turn`、`decide_tool_turn` 把策略判断从 `agent_loop.py` 抽离。失败或空工具结果不能支持过早 final，基础预算耗尽且当前结果必须继续时默认只增加 1 步，调用方也可用 `widening_extra_steps=0` 保持严格上限。2026-07-20 的全量测试结果为 `156 passed, 1 skipped`，跳过项仍是需要显式启用的 live Qwen 测试。

- 学习总结：[`stage-13-turn-kernel-policies.md`](docs/stage-summaries/stage-13-turn-kernel-policies.md)

## 阶段 14：技能和扩展点

目标：理解 MiniCode 如何从固定工具扩展到技能和 MCP，但只做可测试的最小版本。

### 先跑通最小闭环

- 实现 `skills.py`：
  - 在项目目录发现 `SKILL.md`。
  - 返回技能元数据。
  - `load_skill` 工具读取指定技能。
- MCP 先不做真实 stdio，只实现 fake registry 或留接口。

### 对照真实模块理解

- 对照 `minicode/skills.py`。
- 对照 `minicode/tools/load_skill.py`。
- 对照 `minicode/mcp.py`，只理解它为什么是可选工具来源。

### 写测试验证

- 临时目录中创建技能后可以发现。
- `load_skill` 能读取内容。
- 没有技能时返回空列表。
- fake MCP 工具可以注册到 ToolRegistry。

### Git 上传

- 提交信息：`stage-14: add skills extension point`
- 标签：`stage-14`
- 推送 GitHub/Gitee。

### 完成状态（已完成）

阶段 14 已实现项目、用户和兼容目录的技能发现，使用轻量元数据注入 prompt，并通过 `load_skill` 工具按需读取正文。技能名称和符号链接都受根目录边界约束；同名技能按项目优先级确定。fake MCP 工具可批量、原子地接入 `ToolRegistry`，真实 stdio MCP 按计划后置。2026-07-20 的全量测试结果为 `167 passed, 1 skipped`，跳过项仍是需显式启用的 live Qwen 测试。

- 学习总结：[`stage-14-skills-extension-point.md`](docs/stage-summaries/stage-14-skills-extension-point.md)

## 阶段 15：轻量 TUI 或交互式 REPL

目标：不追求完整全屏 TUI，先做可用的交互式体验，理解 transcript 和 tool lifecycle。

### 先跑通最小闭环

- 实现一个简单 REPL：
  - 读取用户输入。
  - 本地命令直接执行。
  - 普通输入进入 agent turn。
  - 展示 tool start/tool result/assistant。
  - `/exit` 退出。

### 对照真实模块理解

- 对照 `minicode/tty_app.py`，只看运行主循环。
- 对照 `minicode/tui/input_handler.py`，理解输入如何分流。
- 对照 `minicode/tui/tool_lifecycle.py`，理解工具状态如何进入 transcript。
- 暂不复制 alt-screen、滚动、主题、markdown 渲染。

### 写测试验证

- 输入解析函数测试。
- 本地命令分流测试。
- transcript 追加顺序测试。
- dangling running tool 能被标记错误。

### Git 上传

- 提交信息：`stage-15: add interactive repl surface`
- 标签：`stage-15`
- 推送 GitHub/Gitee。

### 完成状态（已完成）

阶段 15 已实现同步行模式的轻量 REPL：输入被分类为退出、本地命令或 agent 任务；本地命令继续复用统一命令处理器，普通输入进入持续的 agent/session 状态；工具 start/result/error 和 assistant 按顺序进入可观察 transcript。退出时悬挂的 running 工具会被标记为 error。提供 `python -m minicode_lite --repl` 与 `minicode-lite-repl` 入口，未引入全屏重绘、raw mode 或后台线程。全量测试结果记录在阶段总结中。

- 学习总结：[`stage-15-interactive-repl-surface.md`](docs/stage-summaries/stage-15-interactive-repl-surface.md)

## 阶段 16：集成测试和发布门禁

目标：把前面分散的能力组合起来，形成真正可回归的 MiniCode Lite harness。

### 先跑通最小闭环

- 建立 `tests/test_integration.py`：
  - mock model 发起读文件。
  - 工具返回结果。
  - agent 最终回答。
  - session 保存。
  - replay 可读。
- 建立最小 release checklist：
  - compile/import。
  - pytest。
  - readiness JSON。
  - headless smoke。

### 对照真实模块理解

- 对照 `tests/test_integration.py`、`tests/test_integration_rounds.py`。
- 对照 `minicode/release_readiness.py`。
- 对照 `minicode/structure_check.py`，理解结构门禁的意义，但不急着实现同等复杂度。

### 写测试验证

- 端到端测试覆盖：
  - prompt -> tool -> final。
  - write -> checkpoint -> rewind。
  - session -> replay。
  - readiness。
- 增加一个 Windows 路径相关测试。

### Git 上传

- 提交信息：`stage-16: add integration and release checks`
- 标签：`stage-16`
- 推送 GitHub/Gitee。

阶段 16 已建立真实跨模块回归链路：`tests/test_integration.py` 覆盖 prompt -> tool -> final -> session -> replay、write -> checkpoint -> rewind、readiness JSON 和 Windows 反斜杠路径；`release_gate.py` 将 compile、import、pytest、readiness JSON 与离线 headless smoke 汇总为稳定报告和退出码。2026-07-20 的全量测试结果为 `178 passed, 1 skipped`，五项真实发布门禁均通过。

- 学习总结：[`stage-16-integration-and-release-gates.md`](docs/stage-summaries/stage-16-integration-and-release-gates.md)

## 阶段 17：回顾真实 MiniCode-Python 架构

目标：在自己已经实现一遍后，再系统回看真实项目，补齐理解而不是盲目复制。

### 先跑通最小闭环

- 跑通本项目全部测试。
- 用本项目 headless 分析自己的仓库。
- 用本项目 replay 查看一次会话。

### 对照真实模块理解

- 重新阅读 `Docs/Documentation/STRUCTURE.md`。
- 对照自己的模块和真实模块，写一份 `ARCHITECTURE_NOTES.md`：
  - 哪些是核心路径。
  - 哪些是产品面。
  - 哪些是高级优化层。
  - 哪些暂时不该复制。
- 建议重点比较：
  - `agent_loop.py`
  - `turn_kernel.py`
  - `tooling.py`
  - `permissions.py`
  - `session.py`
  - `readiness.py`

### 写测试验证

- 不新增大功能，只补测试缺口。
- 将真实项目的关键测试思想迁移到本项目：
  - 脚本化模型。
  - fake tool。
  - tmp_path。
  - permission prompt mock。
  - provider unavailable mock。

### Git 上传

- 提交信息：`stage-17: document architecture comparison`
- 标签：`stage-17`
- 推送 GitHub/Gitee。

## 阶段完成定义

一个阶段只有同时满足以下条件，才算完成：

- 该阶段最小闭环可以手动跑通。
- 该阶段至少有一组自动化测试。
- 已阅读并记录对应真实 MiniCode-Python 模块差异。
- 已生成对应阶段学习总结文档，路径为 `docs/stage-summaries/stage-XX-<阶段主题>.md`。
- `python -m pytest -q` 通过。
- 已 commit、tag、push 到 GitHub/Gitee。

## 推荐学习顺序总览

| 阶段 | 主题 | 最小闭环关键词 | 对照模块 | 测试重点 |
|---|---|---|---|---|
| 0 | 脚手架 | import + CLI smoke | `pyproject.toml`, `main.py` | 包导入 |
| 1 | 类型和 mock 模型 | prompt -> assistant | `types.py`, `mock_model.py` | scripted model |
| 2 | 工具注册表 | tool name -> result | `tooling.py` | validator/error |
| 3 | agent loop | model -> tool -> model | `agent_loop.py`, `turn_kernel.py` | tool_result/final |
| 4 | 文件工具 | read/write/edit | `workspace.py`, `tools/` | tmp_path/path guard |
| 5 | CLI/headless | command -> answer | `main.py`, `headless.py` | subprocess/headless |
| 6 | prompt/config/model registry | runtime -> Qwen/mock model | `config.py`, `prompt.py`, `model_registry.py` | env/settings/fake client |
| 7 | 权限/命令 | safe command gate | `permissions.py`, `run_command.py` | dangerous command |
| 8 | session/replay | save -> load -> replay | `session.py` | persistence |
| 9 | checkpoint/rewind | write -> snapshot -> restore | `session.py`, `file_review.py` | restore disk |
| 10 | memory | add -> retrieve -> inject | `memory.py` | persistence/search |
| 11 | 本地命令 | `/session` 等 | `cli_commands.py` | command formatting |
| 12 | readiness/logging | report runtime state | `readiness.py` | JSON schema |
| 13 | turn kernel | phase/verify/widen | `turn_kernel.py` | policy decisions |
| 14 | skills | discover/load skill | `skills.py` | temp SKILL.md |
| 15 | REPL/TUI | interactive loop | `tty_app.py`, `tui/` | input/transcript |
| 16 | 集成门禁 | e2e smoke | integration tests | full flow |
| 17 | 架构回顾 | compare notes | `STRUCTURE.md` | test gaps |

## 不要过早实现的内容

这些在真实 MiniCode-Python 里很重要，但对从 0 理解 harness 来说应该后置：

- 完整 TUI 渲染、alt-screen、滚动、主题。
- Anthropic/OpenAI 真实 provider streaming。
- MCP stdio 完整协议。
- 控制论 PID、自愈、预测控制、复杂 compaction。
- release readiness 的全量 artifact bundle。
- 大规模 memory reranker 和向量检索。

先把可测、可回放、可恢复的核心 harness 做稳，再逐个接入高级能力。
