# 阶段 0-5 教学注释实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为阶段 0-5 的 `minicode_lite/` 运行时代码补充简体中文教学注释，并将规范固化到项目规则中。

**Architecture:** 保持现有模块、类型、函数签名和运行时流程不变，仅补充模块说明、函数说明与行内中文注释。核心 harness 模块按逻辑行解释消息、工具、工作区和循环；其余模块说明职责、输入输出、关键分支与错误边界。

**Tech Stack:** Python 3、pytest、Git。

---

## 文件职责映射

- `minicode_lite/types.py`：定义模型与 agent loop 共享的消息和步骤契约。
- `minicode_lite/tooling.py`：定义工具、工具上下文与工具执行边界。
- `minicode_lite/agent_loop.py`：驱动模型、工具和消息历史的单轮循环。
- `minicode_lite/workspace.py`、`minicode_lite/tools/_shared.py`：守住工作区路径和 UTF-8 文件访问边界。
- `minicode_lite/mock_model.py`：提供可预测的测试/演示模型。
- `minicode_lite/headless.py`、`local_commands.py`、`main.py`：提供命令行入口、本地命令和单轮执行。
- `minicode_lite/tools/*.py`：定义默认文件工具及其输入校验和执行过程。
- `minicode_lite/__init__.py`、`__main__.py`：暴露包版本并支持 `python -m` 调用。
- `AGENTS.md`：保存后续阶段必须遵守的注释规范。

### Task 1: 注释核心 harness 与工作区边界

**Files:**
- Modify: `minicode_lite/types.py`
- Modify: `minicode_lite/tooling.py`
- Modify: `minicode_lite/agent_loop.py`
- Modify: `minicode_lite/workspace.py`
- Modify: `minicode_lite/tools/_shared.py`
- Test: `tests/test_types.py`, `tests/test_tooling.py`, `tests/test_agent_loop.py`, `tests/test_workspace.py`, `tests/test_tools.py`

- [ ] **Step 1: 为每个核心模块补充中文职责说明**

在文件开头解释该模块在最小 harness 闭环中的位置：类型是契约，工具注册表是调度台，agent loop 是主循环，workspace 是路径护栏，共享文件函数负责把文件系统错误转成 `ToolResult`。

- [ ] **Step 2: 对核心对象和每条逻辑语句添加中文注释**

逐逻辑行解释 `TypedDict` 字段、`dataclass` 默认值、协议方法签名、工具查找和验证、异常转换、消息快照、assistant/tool 消息写入、空响应重试、最大步骤停止、路径归一化与 `relative_to` 越界检查、UTF-8 读写和二进制判定。

- [ ] **Step 3: 检查核心文件语法与回归行为**

Run: `python -m pytest -q tests/test_types.py tests/test_tooling.py tests/test_agent_loop.py tests/test_workspace.py tests/test_tools.py`

Expected: 全部通过；注释不改变既有返回值、消息顺序或路径安全行为。

### Task 2: 注释模型、文件工具与命令行执行路径

**Files:**
- Modify: `minicode_lite/mock_model.py`
- Modify: `minicode_lite/headless.py`
- Modify: `minicode_lite/local_commands.py`
- Modify: `minicode_lite/main.py`
- Modify: `minicode_lite/tools/list_files.py`
- Modify: `minicode_lite/tools/read_file.py`
- Modify: `minicode_lite/tools/write_file.py`
- Modify: `minicode_lite/tools/edit_file.py`
- Modify: `minicode_lite/tools/patch_file.py`
- Modify: `minicode_lite/tools/__init__.py`
- Test: `tests/test_mock_model.py`, `tests/test_headless.py`, `tests/test_cli_stage5.py`, `tests/test_tools.py`

- [ ] **Step 1: 为模型和 CLI 函数加入教学说明**

解释 `ScriptedModel` 如何按顺序提供预设步骤，`MockModelAdapter` 如何用最近用户消息或工具结果构造确定性回复；解释 headless 的空 prompt 拒绝、本地命令优先分流、初始消息创建和最终 assistant 消息提取；解释 CLI 的版本、无参数 smoke 和有 prompt 的单轮分支。

- [ ] **Step 2: 为每个文件工具的校验与执行关键行加入中文注释**

解释输入对象校验、默认路径、路径解析结果、文件/目录分支、排序、`assert` 用于缩窄可选值、换行标准化、单次/全部替换的差异、匹配数保护、多段补丁的顺序应用和统一的 `ToolDefinition` 注册。

- [ ] **Step 3: 检查命令与文件工具回归行为**

Run: `python -m pytest -q tests/test_mock_model.py tests/test_headless.py tests/test_cli_stage5.py tests/test_tools.py`

Expected: 全部通过；`/tools`、`/read`、文件编辑与补丁、CLI/headless 输出保持不变。

### Task 3: 注释包入口并固化项目规则

**Files:**
- Modify: `minicode_lite/__init__.py`
- Modify: `minicode_lite/__main__.py`
- Modify: `AGENTS.md`
- Test: `tests/test_smoke.py`, `tests/test_cli_stage5.py`

- [ ] **Step 1: 为包元数据和模块入口补充简短中文注释**

说明 `__all__` 限制公开导出、`__version__` 供 CLI 使用，以及 `__main__.py` 如何将 `python -m minicode_lite` 转交给 CLI 主函数并转换退出码。

- [ ] **Step 2: 在 AGENTS.md 新增持久化注释规范**

写明后续所有阶段的运行时代码必须使用简体中文教学注释；核心模块/函数解释每条逻辑语句；非核心模块/函数至少解释职责、输入输出、关键分支和边界；测试文件不要求逐行注释；注释必须与代码行为一致且避免重复语法表面含义。

- [ ] **Step 3: 运行入口相关回归测试**

Run: `python -m pytest -q tests/test_smoke.py tests/test_cli_stage5.py`

Expected: 全部通过；包导入、`python -m` 入口和既有 CLI 行为不变。

### Task 4: 整体验证与阶段化 Git 收尾

**Files:**
- Modify: 上述所有运行时代码、`AGENTS.md`、本计划文档
- Test: `tests/`

- [ ] **Step 1: 检查改动只包含注释、规则和计划文件**

Run: `git diff --check` 和 `git diff -- minicode_lite AGENTS.md`

Expected: 没有空白错误；运行时代码的可执行语句、字符串常量、函数签名和控制流未被修改。

- [ ] **Step 2: 运行完整回归测试**

Run: `python -m pytest -q`

Expected: 所有测试通过。

- [ ] **Step 3: 提交并推送注释改造**

Run: `git add minicode_lite AGENTS.md docs/superpowers/plans/2026-07-13-stage-00-05-teaching-comments.md`, `git commit -m "docs: add Chinese teaching comments for stages 0-5"`, `git tag stage-05-comments`, `git push github main --tags`, `git push gitee main --tags`。

Expected: 工作区干净，两个远端均包含提交和 `stage-05-comments` 标签。
