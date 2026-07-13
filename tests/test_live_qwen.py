from __future__ import annotations

import pytest

from minicode_lite.config import load_runtime_config
from minicode_lite.model_registry import create_model_adapter
from minicode_lite.tooling import ToolRegistry


@pytest.mark.live_qwen
def test_live_qwen_returns_an_assistant_response() -> None:
    """在显式启用且配置完整时，验证真实 Qwen endpoint 能返回标准步骤。"""

    config = load_runtime_config()
    if not config.live_qwen_test_enabled or not config.is_qwen_configured:
        pytest.skip("Live Qwen test requires MINICODE_LITE_LIVE_QWEN_TEST=1 and complete runtime configuration.")

    adapter, _diagnostic = create_model_adapter(config, ToolRegistry([]))

    step = adapter.next([{"role": "user", "content": "MiniCode Lite Qwen connected."}])

    assert step.type == "assistant"
    assert step.content
