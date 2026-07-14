# Stage 06 Runtime Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add configurable Qwen/DashScope runtime support while preserving the mock model as the default safe fallback.

**Architecture:** `RuntimeConfig` is the single source of resolved configuration, and `model_registry` is the only model-selection boundary.  `QwenModelAdapter` uses a standard-library HTTP transport behind an injectable callable so request mapping is covered without network access; `headless` supplies a generated system prompt and the selected adapter to the existing loop.

**Tech Stack:** Python 3.11 standard library (`dataclasses`, `json`, `os`, `pathlib`, `urllib`), pytest, DashScope OpenAI-compatible Chat Completions API.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `minicode_lite/config.py` | Resolve settings JSON, `.env`, and process environment into `RuntimeConfig`. |
| `minicode_lite/prompt.py` | Build the runtime system prompt from cwd, tools, and explicit placeholders. |
| `minicode_lite/qwen_adapter.py` | Map local history/tools to OpenAI-compatible JSON and parse responses into `AgentStep`. |
| `minicode_lite/model_registry.py` | Select Qwen only when configuration is complete, otherwise select mock. |
| `minicode_lite/headless.py` | Build a system message and select its model through the registry. |
| `tests/test_config.py` | Cover settings source precedence and fallback diagnostics. |
| `tests/test_prompt.py` | Cover prompt runtime-context rendering. |
| `tests/test_qwen_adapter.py` | Cover outbound protocol shape and inbound response/error mapping with a fake transport. |
| `tests/test_model_registry.py` | Cover adapter selection and complete/incomplete configurations. |
| `tests/test_headless.py` | Cover headless use of the registry and generated system message. |
| `tests/test_live_qwen.py` | Make one gated real DashScope request after `.env` contains a key. |
| `.env` | Ignored local Qwen credentials and live-test flag. |
| `.env.example` | Committable credential-free configuration template. |
| `pyproject.toml` | Register the `live_qwen` pytest marker. |
| `docs/stage-summaries/stage-06-prompt-config-qwen-model-adapter.md` | Required teaching summary for the stage. |
| `MINICODE_HARNESS_LEARNING_PLAN.md` | Record that Stage 06 is complete. |

### Task 1: Resolve Runtime Configuration

**Files:**
- Create: `minicode_lite/config.py`
- Create: `tests/test_config.py`
- Create: `.env`
- Create: `.env.example`

- [ ] **Step 1: Write failing configuration tests**

```python
from __future__ import annotations

import json

from minicode_lite.config import load_runtime_config


def test_process_environment_overrides_dotenv_and_settings(tmp_path, monkeypatch) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps({"model": "settings-model", "base_url": "https://settings.example/v1", "api_key": "settings-key"}),
        encoding="utf-8",
    )
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "MINI_CODE_MODEL=dotenv-model\\nCUSTOM_API_BASE_URL=https://dotenv.example/v1\\nCUSTOM_API_KEY=dotenv-key\\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MINI_CODE_MODEL", "process-model")
    monkeypatch.setenv("CUSTOM_API_BASE_URL", "https://process.example/v1/")
    monkeypatch.setenv("CUSTOM_API_KEY", "process-key")

    config = load_runtime_config(settings_path=settings_path, dotenv_path=dotenv_path)

    assert config.model == "process-model"
    assert config.base_url == "https://process.example/v1"
    assert config.api_key == "process-key"
    assert config.is_qwen_configured is True


def test_settings_are_used_when_higher_priority_sources_are_missing(tmp_path, monkeypatch) -> None:
    for name in ("MINI_CODE_MODEL", "CUSTOM_API_BASE_URL", "CUSTOM_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps({"model": "qwen3.7-max", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "api_key": "settings-key"}),
        encoding="utf-8",
    )

    config = load_runtime_config(settings_path=settings_path, dotenv_path=tmp_path / "missing.env")

    assert config.model == "qwen3.7-max"
    assert config.is_qwen_configured is True


def test_missing_provider_values_describe_mock_fallback(tmp_path, monkeypatch) -> None:
    for name in ("MINI_CODE_MODEL", "CUSTOM_API_BASE_URL", "CUSTOM_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    config = load_runtime_config(settings_path=tmp_path / "missing.json", dotenv_path=tmp_path / "missing.env")

    assert config.is_qwen_configured is False
    assert "CUSTOM_API_KEY" in config.diagnostic
```

- [ ] **Step 2: Run the new tests and verify the expected import failure**

Run: `python -m pytest tests/test_config.py -q`

Expected: collection fails with `ModuleNotFoundError: No module named 'minicode_lite.config'`.

- [ ] **Step 3: Implement the minimal configuration loader with Chinese teaching comments**

```python
@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    model: str
    base_url: str
    api_key: str
    diagnostic: str

    @property
    def is_qwen_configured(self) -> bool:
        return bool(self.model and self.base_url and self.api_key)


def load_runtime_config(
    *, settings_path: Path | None = None, dotenv_path: Path | None = None
) -> RuntimeConfig:
    settings = _load_json_settings(settings_path)
    dotenv = _load_dotenv(dotenv_path)
    model = os.environ.get("MINI_CODE_MODEL", dotenv.get("MINI_CODE_MODEL", settings.get("model", ""))).strip()
    base_url = _normalize_base_url(os.environ.get("CUSTOM_API_BASE_URL", dotenv.get("CUSTOM_API_BASE_URL", settings.get("base_url", ""))))
    api_key = os.environ.get("CUSTOM_API_KEY", dotenv.get("CUSTOM_API_KEY", settings.get("api_key", ""))).strip()
    missing = [name for name, value in (("MINI_CODE_MODEL", model), ("CUSTOM_API_BASE_URL", base_url), ("CUSTOM_API_KEY", api_key)) if not value]
    diagnostic = "Qwen runtime configured." if not missing else f"Using mock model because missing: {', '.join(missing)}."
    return RuntimeConfig(model=model, base_url=base_url, api_key=api_key, diagnostic=diagnostic)
```

Implement `_load_dotenv` as a small `KEY=value` parser that ignores blank/comment lines and never mutates `os.environ`; implement `_load_json_settings` to return `{}` for a missing file and raise `ValueError` for invalid JSON/object shape; implement `_normalize_base_url` with `rstrip('/')`.

- [ ] **Step 4: Add the local and shareable configuration files**

```dotenv
# .env (ignored; fill CUSTOM_API_KEY locally after implementation)
MINI_CODE_MODEL=qwen3.7-max
CUSTOM_API_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
CUSTOM_API_KEY=
MINICODE_LITE_LIVE_QWEN_TEST=1
```

```dotenv
# .env.example (committed; never place a real key here)
MINI_CODE_MODEL=qwen3.7-max
CUSTOM_API_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
CUSTOM_API_KEY=
MINICODE_LITE_LIVE_QWEN_TEST=1
```

- [ ] **Step 5: Run the configuration tests and verify they pass**

Run: `python -m pytest tests/test_config.py -q`

Expected: `3 passed`.

- [ ] **Step 6: Commit the configuration boundary**

```powershell
git add minicode_lite/config.py tests/test_config.py .env.example
git commit -m "stage-06: add runtime configuration loader"
```

### Task 2: Build a Dynamic System Prompt

**Files:**
- Create: `minicode_lite/prompt.py`
- Create: `tests/test_prompt.py`

- [ ] **Step 1: Write the failing prompt test**

```python
from minicode_lite.prompt import build_system_prompt
from minicode_lite.tooling import ToolDefinition, ToolRegistry, ToolResult


def test_system_prompt_contains_runtime_context() -> None:
    registry = ToolRegistry([
        ToolDefinition(
            name="echo",
            description="Echo a text value.",
            input_schema={"type": "object"},
            validator=lambda value: value,
            run=lambda _value, _context: ToolResult(ok=True, output="ok"),
        )
    ])

    prompt = build_system_prompt(cwd="C:/workspace/demo", tools=registry)

    assert "C:/workspace/demo" in prompt
    assert "echo" in prompt
    assert "Echo a text value." in prompt
    assert "Permissions: not configured" in prompt
    assert "Memory: not configured" in prompt
```

- [ ] **Step 2: Run the test and verify the expected import failure**

Run: `python -m pytest tests/test_prompt.py -q`

Expected: collection fails with `ModuleNotFoundError: No module named 'minicode_lite.prompt'`.

- [ ] **Step 3: Implement the smallest prompt builder with Chinese teaching comments**

```python
def build_system_prompt(*, cwd: str, tools: ToolRegistry) -> str:
    tool_lines = [f"- {tool.name}: {tool.description}" for tool in tools.list()]
    rendered_tools = "\\n".join(tool_lines) if tool_lines else "- No tools registered."
    return "\\n".join(
        [
            "You are MiniCode Lite, a coding assistant.",
            f"Current working directory: {cwd}",
            "Available tools:",
            rendered_tools,
            "Permissions: not configured",
            "Memory: not configured",
        ]
    )
```

- [ ] **Step 4: Run the prompt test and verify it passes**

Run: `python -m pytest tests/test_prompt.py -q`

Expected: `1 passed`.

- [ ] **Step 5: Commit the prompt boundary**

```powershell
git add minicode_lite/prompt.py tests/test_prompt.py
git commit -m "stage-06: add runtime system prompt"
```

### Task 3: Map Qwen Requests and Responses

**Files:**
- Create: `minicode_lite/qwen_adapter.py`
- Create: `tests/test_qwen_adapter.py`

- [ ] **Step 1: Write failing adapter tests using a fake transport**

```python
from minicode_lite.qwen_adapter import QwenModelAdapter
from minicode_lite.tooling import ToolDefinition, ToolRegistry, ToolResult


def _tools() -> ToolRegistry:
    return ToolRegistry([ToolDefinition(
        name="echo", description="Echo text.", input_schema={"type": "object"},
        validator=lambda value: value, run=lambda _value, _context: ToolResult(ok=True, output="ok"),
    )])


def test_adapter_sends_openai_compatible_request_and_parses_text() -> None:
    captured = {}

    def transport(url, headers, payload):
        captured.update(url=url, headers=headers, payload=payload)
        return {"choices": [{"message": {"content": "hello from qwen"}}]}

    adapter = QwenModelAdapter(model="qwen3.7-max", base_url="https://dashscope.example/v1", api_key="key", tools=_tools(), transport=transport)

    step = adapter.next([{"role": "system", "content": "system"}, {"role": "user", "content": "hello"}])

    assert captured["url"] == "https://dashscope.example/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer key"
    assert captured["payload"]["model"] == "qwen3.7-max"
    assert captured["payload"]["tools"][0]["function"]["name"] == "echo"
    assert step.content == "hello from qwen"


def test_adapter_parses_provider_tool_calls() -> None:
    adapter = QwenModelAdapter(
        model="qwen3.7-max", base_url="https://dashscope.example/v1", api_key="key", tools=ToolRegistry([]),
        transport=lambda _url, _headers, _payload: {"choices": [{"message": {"tool_calls": [{"id": "call-1", "function": {"name": "echo", "arguments": "{\\\"text\\\": \\\"hi\\\"}"}}]}}]},
    )

    step = adapter.next([{"role": "user", "content": "use echo"}])

    assert step.type == "tool_calls"
    assert step.calls == [{"id": "call-1", "toolName": "echo", "input": {"text": "hi"}}]
```

- [ ] **Step 2: Run the adapter tests and verify the expected import failure**

Run: `python -m pytest tests/test_qwen_adapter.py -q`

Expected: collection fails with `ModuleNotFoundError: No module named 'minicode_lite.qwen_adapter'`.

- [ ] **Step 3: Implement the adapter with an injectable transport and Chinese teaching comments**

```python
class QwenModelAdapter:
    def __init__(self, *, model: str, base_url: str, api_key: str, tools: ToolRegistry, transport: Transport | None = None) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._tools = tools
        self._transport = _default_transport if transport is None else transport

    def next(self, messages: list[ChatMessage], on_stream_chunk=None, store=None) -> AgentStep:
        del on_stream_chunk, store
        response = self._transport(
            f"{self._base_url}/chat/completions",
            {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
            {"model": self._model, "messages": _serialize_messages(messages), "tools": _serialize_tools(self._tools)},
        )
        return _parse_response(response)
```

`_default_transport` must use `urllib.request.Request` and `urlopen`, encode/decode UTF-8 JSON, and raise `RuntimeError` containing the status/body for HTTP failures.  `_serialize_messages` must map local `assistant_tool_call` to an OpenAI assistant `tool_calls` message and local `tool_result` to an OpenAI `tool` message.  `_parse_response` must reject missing choices/message, turn a non-empty `content` string into an assistant step, parse each tool-call `arguments` JSON object, and reject neither-text-nor-tools responses with `RuntimeError`.

- [ ] **Step 4: Run adapter tests and verify they pass**

Run: `python -m pytest tests/test_qwen_adapter.py -q`

Expected: `2 passed`.

- [ ] **Step 5: Commit the protocol adapter**

```powershell
git add minicode_lite/qwen_adapter.py tests/test_qwen_adapter.py
git commit -m "stage-06: add qwen compatible model adapter"
```

### Task 4: Select the Adapter and Wire Headless Mode

**Files:**
- Create: `minicode_lite/model_registry.py`
- Create: `tests/test_model_registry.py`
- Modify: `minicode_lite/headless.py`
- Modify: `tests/test_headless.py`

- [ ] **Step 1: Write failing registry and headless tests**

```python
from minicode_lite.config import RuntimeConfig
from minicode_lite.model_registry import create_model_adapter
from minicode_lite.mock_model import MockModelAdapter
from minicode_lite.qwen_adapter import QwenModelAdapter
from minicode_lite.tooling import ToolRegistry


def test_registry_uses_mock_for_incomplete_configuration() -> None:
    adapter, diagnostic = create_model_adapter(
        RuntimeConfig(model="qwen3.7-max", base_url="", api_key="", diagnostic="missing"), ToolRegistry([])
    )

    assert isinstance(adapter, MockModelAdapter)
    assert diagnostic == "missing"


def test_registry_uses_qwen_for_complete_configuration() -> None:
    adapter, diagnostic = create_model_adapter(
        RuntimeConfig(model="qwen3.7-max", base_url="https://dashscope.example/v1", api_key="key", diagnostic="configured"), ToolRegistry([])
    )

    assert isinstance(adapter, QwenModelAdapter)
    assert diagnostic == "configured"
```

```python
def test_run_headless_prepends_system_prompt_and_uses_registry(tmp_path, monkeypatch) -> None:
    received = {}

    class RecordingModel:
        def next(self, messages, on_stream_chunk=None, store=None):
            received["messages"] = messages
            return AgentStep(type="assistant", content="registry response")

    monkeypatch.setattr("minicode_lite.headless.create_model_adapter", lambda _config, _tools: (RecordingModel(), "mock"))

    assert run_headless("hello", cwd=tmp_path) == "registry response"
    assert received["messages"][0]["role"] == "system"
    assert str(tmp_path) in received["messages"][0]["content"]
```

- [ ] **Step 2: Run the tests and verify expected failures**

Run: `python -m pytest tests/test_model_registry.py tests/test_headless.py -q`

Expected: collection fails with `ModuleNotFoundError: No module named 'minicode_lite.model_registry'`, then the new headless test fails because `create_model_adapter` is not imported by `headless`.

- [ ] **Step 3: Implement the registry and headless integration with Chinese teaching comments**

```python
def create_model_adapter(config: RuntimeConfig, tools: ToolRegistry) -> tuple[ModelAdapter, str]:
    if not config.is_qwen_configured:
        return MockModelAdapter(), config.diagnostic
    return (
        QwenModelAdapter(
            model=config.model,
            base_url=config.base_url,
            api_key=config.api_key,
            tools=tools,
        ),
        config.diagnostic,
    )
```

In `run_headless`, replace `MockModelAdapter()` with `config = load_runtime_config()` and `model, _diagnostic = create_model_adapter(config, tools)`.  Replace the initial messages list with a system message from `build_system_prompt(cwd=str(workspace), tools=tools)` followed by the existing user message.  Preserve local-command short-circuiting before any config/model construction.

- [ ] **Step 4: Run registry and headless tests and verify they pass**

Run: `python -m pytest tests/test_model_registry.py tests/test_headless.py -q`

Expected: all selected tests pass, including the three existing headless tests.

- [ ] **Step 5: Commit runtime selection and entry-point wiring**

```powershell
git add minicode_lite/model_registry.py minicode_lite/headless.py tests/test_model_registry.py tests/test_headless.py
git commit -m "stage-06: wire configurable model into headless mode"
```

### Task 5: Add Real Qwen Verification and Stage Learning Materials

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/test_live_qwen.py`
- Create: `docs/stage-summaries/stage-06-prompt-config-qwen-model-adapter.md`
- Modify: `MINICODE_HARNESS_LEARNING_PLAN.md`

- [ ] **Step 1: Add the marker and write the gated live integration test**

```toml
[tool.pytest.ini_options]
markers = [
  "live_qwen: calls the configured DashScope Qwen endpoint and may consume API quota",
]
```

```python
from __future__ import annotations

import os

import pytest

from minicode_lite.config import load_runtime_config
from minicode_lite.model_registry import create_model_adapter
from minicode_lite.tooling import ToolRegistry


@pytest.mark.live_qwen
def test_live_qwen_returns_non_empty_assistant_message() -> None:
    config = load_runtime_config()
    enabled = os.environ.get("MINICODE_LITE_LIVE_QWEN_TEST") == "1"
    if not enabled or not config.is_qwen_configured:
        pytest.skip("set CUSTOM_API_KEY and MINICODE_LITE_LIVE_QWEN_TEST=1 in .env to run this test")

    model, _diagnostic = create_model_adapter(config, ToolRegistry([]))
    step = model.next([{"role": "user", "content": "Reply with exactly: MiniCode Lite Qwen connected."}])

    assert step.type == "assistant"
    assert step.content.strip()
```

- [ ] **Step 2: Run the live test before adding a key and verify it skips**

Run: `python -m pytest tests/test_live_qwen.py -q`

Expected: `1 skipped` because `.env` has no `CUSTOM_API_KEY`.

- [ ] **Step 3: Write the required stage learning summary and update plan progress**

The summary must use the stage template and include the required sections: topic, problem, solution, working principle, reference material, learning outcomes, test verification, differences from MiniCode-Python, review prompts, and the transition to Stage 07.  Add a concise data-flow diagram showing configuration sources, registry fallback, adapter, and agent loop.  Explain that Stage 07 replaces the permissions placeholder with real approval boundaries.

Add a Stage 06 completion entry to `MINICODE_HARNESS_LEARNING_PLAN.md` that links the summary and records the final tag `stage-06`.

- [ ] **Step 4: Run the complete offline suite and verify it passes**

Run: `python -m pytest -q`

Expected: all unit tests pass and the live test skips until the key is set.

- [ ] **Step 5: After filling `.env`, run the real DashScope check**

Set `CUSTOM_API_KEY=sk-...` in ignored `.env`, leaving `MINICODE_LITE_LIVE_QWEN_TEST=1`.

Run: `python -m pytest tests/test_live_qwen.py -m live_qwen -q`

Expected: `1 passed`; the test must not print or assert the secret key.

- [ ] **Step 6: Commit and tag the completed stage**

```powershell
git add pyproject.toml tests/test_live_qwen.py docs/stage-summaries/stage-06-prompt-config-qwen-model-adapter.md MINICODE_HARNESS_LEARNING_PLAN.md .env.example
git commit -m "stage-06: add prompt config and qwen model adapter"
git tag stage-06
```

## Plan Self-Review

- Spec coverage: Task 1 implements `.env`, JSON, process-environment precedence, safe fallback diagnostics, and the requested configuration key names. Task 2 implements the dynamic prompt. Task 3 implements text/tool-call protocol mapping and transport errors. Task 4 makes the registry the selection boundary and routes headless through it. Task 5 provides both offline and opt-in real DashScope validation plus all required learning documentation.
- Placeholder scan: every task states its concrete implementation and expected verification outcome.
- Type consistency: `RuntimeConfig`, `load_runtime_config`, `build_system_prompt`, `QwenModelAdapter`, and `create_model_adapter` use the same names and argument order in every task.
