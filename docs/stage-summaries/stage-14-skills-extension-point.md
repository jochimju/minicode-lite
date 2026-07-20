# 阶段 14：技能和扩展点学习总结

## 主题

本阶段把“固定写死的工具”扩展为“项目可以声明自己的技能，并按需提供给 agent”。大白话讲，工具像扳手，技能像一页写着工作流程和注意事项的操作卡；agent 先看到卡片目录，需要时再打开指定卡片。

## 问题是什么

没有技能发现机制时，每个项目的约定只能硬编码进 prompt 或 Python 模块，既难复用，也会让 system prompt 变得很大。没有扩展点时，外部 MCP 工具又无法复用现有注册、校验、日志和异常边界。

本阶段解决：发现项目和用户技能、返回轻量元数据、按名称安全加载 `SKILL.md`，以及用 fake MCP 证明外部工具可接入 `ToolRegistry`。

## 解决方案

- `skills.py` 支持 `.mini-code/skills/<name>/SKILL.md`，并兼容 `.claude/skills`；项目来源优先于用户来源，同名技能只保留首次发现版本。
- `load_skill` 工具只接受单级目录名，正文按模型请求加载；系统提示只注入名称、描述和来源。
- `mcp.py` 提供 `FakeMcpTool` 和批量注册函数；不启动真实 stdio，批量重名检查失败时保持注册表不变。

## 工作原理

### 心智模型

发现是目录索引，加载是一次受边界保护的读取，注册是把外部能力转换为本地 `ToolDefinition`。三步分开后，prompt 不承担文件读取，agent loop 也不需要知道技能来自哪里。

### 核心对象

#### `SkillSummary` / `LoadedSkill`

前者只保存列表展示所需元数据，后者增加正文，避免每轮都扩大上下文。

#### `discover_skills` / `load_skill`

前者按固定来源顺序扫描并去重，后者校验名称、检查规范化路径仍在技能根目录内，再读取 UTF-8 文本；不可读技能安全跳过或返回 `None`。

#### `create_load_skill_tool`

把读取能力包装为既有工具协议，未知技能和输入错误都返回 `ToolResult(ok=False)`。

#### `FakeMcpTool` / `register_fake_mcp_tools`

用同步函数模拟远端 MCP 调用，转换后仍经过统一 `ToolRegistry.execute`，因此保留日志和异常隔离。

### 当前核心流程

```text
workspace/.mini-code/skills
  -> discover_skills
  -> prompt 注入元数据
  -> agent 请求 load_skill(name)
  -> 路径边界检查 + 读取 SKILL.md
  -> ToolResult 返回正文
```

## 对应核心文档

参考项目 `D:\JavaProject\MiniCode-Python-main`：

- `minicode/skills.py`：对照技能元数据、来源优先级、描述提取和按需读取。
- `minicode/tools/load_skill.py`：对照工具验证与 `ToolResult` 错误返回。
- `minicode/mcp.py`：理解 MCP 是可选工具来源，本阶段只保留适配边界，不复制 stdio 生命周期。

## 学习产出

- `minicode_lite/skills.py`：技能发现、元数据和安全加载。
- `minicode_lite/tools/load_skill.py`：`load_skill` 工具。
- `minicode_lite/mcp.py`：fake MCP 扩展点。
- `minicode_lite/tooling.py`：公开 `ToolRegistry.register` 扩展入口。
- `minicode_lite/prompt.py`、`headless.py`：技能元数据注入和工具注册。
- `tests/test_skills.py`：发现、优先级、越界、工具、fake MCP 和批量原子性测试。

## 测试验证

```powershell
python -m pytest -q
```

结果：`167 passed, 1 skipped`。重点验证了临时目录发现、空目录、同名覆盖、路径遍历、加载工具错误、MCP 重名和 agent/headless prompt 接入；符号链接边界由同一套规范化路径检查保护。

## 和真实 MiniCode-Python 的差异

保留了技能来源优先级、`SKILL.md` 约定、描述与正文分离和工具适配思路。简化为同步本地读取，没有安装/删除技能命令、复杂 front matter、真实 MCP stdio 客户端、连接生命周期、资源和 prompt 能力。

## 常见误区

- 误区：发现技能就等于把所有正文放进 prompt。纠正：发现只给摘要，正文通过 `load_skill` 按需加载。
- 误区：fake MCP 就是真实 MCP。纠正：它只验证注册契约，不能证明进程启动、协议握手或网络可靠性。
- 误区：只检查字符串 `..` 就完成路径安全。纠正：还要规范化并检查符号链接解析后的路径。

## 复习提示

重点理解来源优先级、元数据和正文的上下文成本、工具注册扩展边界，以及为什么批量注册要保持原子性。

自测：技能摘要由谁生成？`load_skill` 为什么拒绝带分隔符的名字？fake MCP 如何复用工具异常隔离？

## 面试高频问题与参考答案

### 1. 技能和工具有什么区别？

**参考答案：** 技能主要是可组合的流程知识和约束，通常由 Markdown 表达；工具是可执行的函数。技能通过 `load_skill` 进入上下文，工具通过 `ToolRegistry.execute` 产生副作用。

### 2. `discover_skills` 为什么只返回摘要？

**参考答案：** 为了控制 prompt 大小和读取成本。列表阶段只需名称、描述、路径和来源，模型明确需要某技能时才加载正文。

### 3. 同名技能如何决定优先级？

**参考答案：** 按项目 `.mini-code`、用户 `.mini-code`、项目 `.claude`、用户 `.claude` 的顺序扫描，字典首次写入即保留高优先级版本，结果也保持稳定顺序。

### 4. 为什么 `load_skill` 拒绝 `folder/name`？

**参考答案：** 工具参数是技能名而不是文件路径。限制为单级目录名可以减少路径注入面，再配合 `resolve().relative_to(root.resolve())` 防止符号链接越界。

### 5. 加载失败为什么不抛出到 agent loop？

**参考答案：** 未知技能和参数错误是模型可修正的输入问题，应转换为 `ToolResult(ok=False)`，让模型看到原因并决定下一步，而不是让整轮崩溃。

### 6. fake MCP 测试验证了什么、没有验证什么？

**参考答案：** 它验证外部工具描述能转换成 `ToolDefinition`，并经过统一注册、执行和结果协议；它没有验证真实 MCP 的 stdio、握手、超时、重连或权限。

### 7. 如果批量注册第二个工具重名，应该如何排查？

**参考答案：** 先检查工具名列表是否内部重复，再检查是否与注册表已有名称冲突，确认注册表列表没有新增半批工具，最后查看 `ToolRegistry` 的名称索引。当前实现预检查全部名称，因此失败应保持原状态。

### 8. 为什么此阶段不直接复制完整 MCP 客户端？

**参考答案：** 阶段目标是理解“可选工具来源如何接入 harness”，不是实现协议栈。fake 适配足以验证边界，真实进程管理和传输故障会在后续有明确需求时单独引入，避免学习闭环被外部系统拖慢。

## 下一阶段衔接

```text
技能发现 -> 按需加载 -> 可测试的外部工具注册
```

下一阶段是轻量 REPL/TUI：它可以展示技能和 MCP 工具的生命周期，并把 `load_skill`、tool start、tool result 追加到 transcript；阶段 14 已提供稳定的工具注册与结果边界。
