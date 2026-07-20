# MiniCode Lite

MiniCode Lite is a learning-first rebuild of the MiniCode Python harness.

The goal is not to copy the full upstream project at once. Instead, this repo
implements the harness in small verified stages:

1. Run the smallest working loop.
2. Compare it with the real `MiniCode-Python-main` module.
3. Write tests that prove the behavior.

The full learning plan is in `MINICODE_HARNESS_LEARNING_PLAN.md`.

## Conda Environment

This project is intended to run in a conda environment:

```powershell
conda activate minicode-lite
python -m pytest -q
python -m minicode_lite
```

To recreate the environment:

```powershell
conda env create -f environment.yml
```

## Local Commands

Local commands are handled before runtime configuration or model creation, so inspection commands also work offline:

| Command | Purpose |
| --- | --- |
| `/tools` | List tools available to the agent. |
| `/readiness [--json]` | Check Python, workspace, tools, and model fallback readiness. |
| `/session [session-id\|latest]` | Inspect the active or latest workspace session. |
| `/sessions` | List saved sessions for the current workspace. |
| `/session-replay [session-id\|latest]` | Replay a session transcript. |
| `/checkpoints [session-id\|latest]` | Show recoverable file checkpoints. |
| `/rewind-preview [latest\|steps\|checkpoint-id]` | Preview a rewind without changing files. |
| `/rewind [latest\|steps\|checkpoint-id]` | Restore files and keep a reverse checkpoint. |
| `/memory` | Show project-memory storage and entry count. |

For example:

```powershell
python -m minicode_lite /sessions
python -m minicode_lite /memory
python -m minicode_lite /readiness --json
```

## Interactive REPL

阶段 15 提供不依赖全屏终端的轻量交互入口：

```powershell
python -m minicode_lite --repl
```

普通输入进入 agent turn，斜杠命令在本地执行，输入 `/exit` 退出。工具事件按
`tool:start -> tool:result/tool:error -> assistant` 的顺序显示。

## Stage 0 Smoke

Expected CLI output:

```text
MiniCode Lite ready
```

## Release Gate

阶段 16 将编译、导入、全量测试、readiness JSON 和离线 headless smoke 组合成一个发布门禁：

```powershell
python -m minicode_lite.release_gate
python -m minicode_lite.release_gate --json
```

只有所有检查都通过时命令才返回退出码 `0`。门禁会强制使用 mock model，并把 smoke session 写入临时目录，因此不会联网、消费 API 配额或污染真实会话。
