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
```

## Stage 0 Smoke

Expected CLI output:

```text
MiniCode Lite ready
```
