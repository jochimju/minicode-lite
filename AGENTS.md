# AGENTS.md

## 项目级持久记忆

本项目 `minicode-lite` 的当前学习目标：参考 `D:\JavaProject\MiniCode-Python-main`，从 0 搭建一个轻量版 MiniCode，用来理解 MiniCode Python 的 harness 工程。

完整学习计划见：

- `MINICODE_HARNESS_LEARNING_PLAN.md`

后续在本项目继续工作时，应先阅读该计划，再按阶段推进。

## 核心原则

每个学习阶段都必须遵循三条原则：

1. 先跑通最小闭环。
2. 对照 MiniCode-Python 真实模块理解。
3. 写测试验证。

## 参考项目

参考项目路径：

- `D:\JavaProject\MiniCode-Python-main`

优先参考这些模块：

- `minicode/types.py`
- `minicode/mock_model.py`
- `minicode/tooling.py`
- `minicode/agent_loop.py`
- `minicode/turn_kernel.py`
- `minicode/workspace.py`
- `minicode/permissions.py`
- `minicode/tools/`
- `minicode/main.py`
- `minicode/headless.py`
- `minicode/session.py`
- `minicode/cli_commands.py`
- `minicode/readiness.py`
- `Docs/Documentation/STRUCTURE.md`
- `tests/test_agent_loop.py`
- `tests/test_tools.py`
- `tests/test_session.py`

## 阶段路线

| 阶段 | 主题 | 当前目标 |
|---|---|---|
| 0 | 项目脚手架和 Git 基线 | 建立可安装、可测试、可提交的空项目 |
| 1 | 核心类型和脚本化模型 | 用 mock/scripted model 替代真实模型 |
| 2 | 工具注册表 | 实现 ToolRegistry、ToolDefinition、ToolResult |
| 3 | 最小 agent loop | 跑通 model -> tool -> model -> final |
| 4 | 工作区和文件工具 | 安全读写当前项目文件 |
| 5 | CLI 和 headless | 从命令行跑单轮任务 |
| 6 | 权限和命令执行 | 建立路径、编辑、命令审批边界 |
| 7 | session 和 replay | 持久化会话并可回放 |
| 8 | checkpoint 和 rewind | 文件修改前留快照并可恢复 |
| 9 | prompt、配置和模型注册 | 形成可配置 runtime |
| 10 | 最小 memory | 项目记忆可写入、检索、注入 |
| 11 | 本地产品命令 | `/session`、`/memory`、`/rewind` 等 |
| 12 | readiness 和日志 | 输出运行时状态和诊断 |
| 13 | turn kernel | phase、verification、widening 策略 |
| 14 | skills 扩展点 | 发现并加载本地技能 |
| 15 | REPL/TUI | 做轻量交互式界面 |
| 16 | 集成测试和发布门禁 | 端到端 smoke 与 release checklist |
| 17 | 架构回顾 | 对照真实 MiniCode-Python 写架构笔记 |

## 每阶段固定收尾

每个阶段完成后必须先生成学习总结文档，再测试、提交、打标签、推送。

学习总结文档路径：

```text
docs/stage-summaries/stage-XX-<阶段主题>.md
```

总结文档必须用于后续复习，至少包含：

- 主题
- 问题是什么
- 解决方案
- 工作原理
- 对应核心文档
- 学习产出
- 测试验证
- 和真实 MiniCode-Python 的差异
- 复习提示
- 下一阶段衔接

可复制模板：

- `docs/stage-summaries/STAGE_SUMMARY_TEMPLATE.md`

收尾命令：

```powershell
python -m pytest -q
git status --short
git add .
git commit -m "stage-XX: <阶段名称>"
git tag stage-XX
git push github main --tags
git push gitee main --tags
```

如果项目只配置了一个远端 `origin`，则改用：

```powershell
git push origin main --tags
```

测试失败不要提交。不要提交 `.env`、API key、真实 session 数据、临时输出。

没有生成阶段学习总结文档时，不要认为该阶段已经完成。

## 当前注意事项

当前工作区里虽然有 `.git` 目录，但 `git status` 未识别为有效仓库。阶段 0 开始前需要先执行 `git init`，并配置 GitHub/Gitee 远端。

本项目实现时不要一开始复制 MiniCode-Python 全量复杂度。优先做核心路径：

```text
entry -> model adapter -> agent loop -> tool registry -> workspace/permissions -> session -> tests
```

控制论、完整 TUI、真实 provider streaming、MCP、复杂 memory 和 release bundle 都应后置。
