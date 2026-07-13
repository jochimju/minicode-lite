from __future__ import annotations

from minicode_lite.config import RuntimeConfig
from minicode_lite.mock_model import MockModelAdapter
from minicode_lite.model_registry import create_model_adapter
from minicode_lite.qwen_adapter import QwenModelAdapter
from minicode_lite.tooling import ToolRegistry


def test_create_model_adapter_uses_mock_for_incomplete_runtime_config() -> None:
    config = RuntimeConfig(
        model="qwen3.7-max",
        base_url="https://example.test/v1",
        api_key="",
        diagnostic="Qwen runtime configuration is incomplete; missing: CUSTOM_API_KEY.",
    )

    adapter, diagnostic = create_model_adapter(config, ToolRegistry([]))

    assert isinstance(adapter, MockModelAdapter)
    assert diagnostic == config.diagnostic


def test_create_model_adapter_uses_qwen_for_complete_runtime_config() -> None:
    config = RuntimeConfig(
        model="qwen3.7-max",
        base_url="https://example.test/v1",
        api_key="test-key",
        diagnostic="Qwen runtime configuration is complete.",
    )
    tools = ToolRegistry([])

    adapter, diagnostic = create_model_adapter(config, tools)

    assert isinstance(adapter, QwenModelAdapter)
    assert diagnostic == config.diagnostic
    assert adapter._tools is tools
