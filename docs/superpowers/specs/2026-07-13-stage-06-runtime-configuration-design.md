# Stage 06 Runtime Configuration Design

## Goal

Stage 06 turns the mock-only runtime into a configurable runtime.  It keeps
the mock model as the safe fallback while allowing an explicitly configured
Qwen model to use DashScope's OpenAI-compatible Chat Completions endpoint.

The user-selected configuration contract is:

```text
MINI_CODE_MODEL=qwen3.7-max
CUSTOM_API_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
CUSTOM_API_KEY=sk-...
```

The real API key lives only in the local, ignored `.env` file.  The repository
contains an `.env.example` with empty values instead.

## Scope

The stage adds five bounded responsibilities:

1. `config.py` loads a local `.env`, optional settings JSON, and process
   environment into a typed runtime configuration.  Process environment has
   the highest priority, followed by `.env`, then JSON settings.  Missing
   provider fields leave the runtime usable in mock mode.
2. `prompt.py` builds the system message from the current working directory,
   registered tools, a permissions-summary placeholder, and a memory
   placeholder.
3. `qwen_adapter.py` converts the project's `ChatMessage` and
   `ToolDefinition` representations to the OpenAI-compatible request shape,
   makes one `/chat/completions` request, and converts an assistant message or
   tool calls back into `AgentStep`.
4. `model_registry.py` is the only model-selection boundary.  Complete Qwen
   configuration creates a `QwenModelAdapter`; incomplete configuration
   returns `MockModelAdapter` together with a clear diagnostic reason.
5. `headless.py` gets its adapter from the registry and prepends the generated
   system prompt before it starts the agent loop.

Streaming, provider failover chains, persisted memory, detailed permissions,
and support for providers other than the configured OpenAI-compatible Qwen
endpoint remain out of scope.

## Configuration Model

`RuntimeConfig` holds the selected model, base URL, API key, settings path,
and a mode/diagnostic value.  Its values are resolved once at startup so
downstream code does not read environment variables itself.

The loader recognizes the user-selected `MINI_CODE_MODEL`,
`CUSTOM_API_BASE_URL`, and `CUSTOM_API_KEY` names.  The settings JSON uses the
same logical fields, but never overrides a value supplied by `.env` or the
process.  The loader does not log API keys.

The base URL is normalized so either a trailing slash or no trailing slash
forms exactly one `/chat/completions` endpoint.

## Adapter Contract

The adapter uses a small injected transport callable rather than an SDK.  Its
default transport is standard-library HTTP; tests replace it with a fake
transport and inspect the full request payload without network access.

Requests contain the configured `model`, converted messages, and converted
tools when a registry supplies tools.  The adapter sends `Authorization:
Bearer <key>` and JSON content headers.  Network, HTTP, and malformed-response
errors become clear adapter errors rather than silently falling back after a
request has started.

An OpenAI-compatible assistant response with text becomes an `assistant`
`AgentStep`.  A response containing `tool_calls` becomes a `tool_calls`
`AgentStep`, preserving each provider-supplied call ID, function name, and JSON
arguments.

## Prompt and Runtime Data Flow

```text
.env / JSON / process environment
             |
             v
       RuntimeConfig ---- incomplete ----> MockModelAdapter
             |
             | complete Qwen configuration
             v
       QwenModelAdapter <---- system prompt + message history + tools
             |
             v
      AgentStep (assistant or tool_calls)
```

`run_headless` creates its tool registry, builds the prompt using its actual
working directory, gets an adapter from the registry, and then runs the
existing agent loop.  This retains the earlier mock behaviour when no local
provider configuration exists.

## Validation Strategy

Tests are split by risk:

- Unit tests cover source precedence, JSON settings loading, missing-config
  fallback, system-prompt content, request endpoint/header/body construction,
  assistant response parsing, tool-call parsing, and error handling.
- A live `pytest` test marked `live_qwen` calls DashScope only when both
  `MINICODE_LITE_LIVE_QWEN_TEST=1` and `CUSTOM_API_KEY` are present.  It sends
  a minimal prompt and asserts a non-empty final assistant result.  Without
  both gates, it is skipped rather than making an accidental billed request.
- The normal suite remains completely offline and must pass without `.env`.

## Teaching and Documentation Requirements

Every changed or new `minicode_lite/` runtime statement receives accurate,
simplified-Chinese teaching comments under this repository's rules.  The stage
also produces the required learning summary comparing this small adapter with
MiniCode-Python's broader model registry and prompt pipeline.

## Explicit Decisions

- Keep `MockModelAdapter` as the default safe fallback.
- Use the user's three environment-variable names as the public contract.
- Use standard-library HTTP and a fake transport for protocol-level tests.
- Keep real network verification opt-in, but make it runnable directly after
  the user fills in `.env` and enables its gate variable.
