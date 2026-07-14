from __future__ import annotations

"""根据运行时配置选择真实 Qwen 适配器或稳定的 mock 后备适配器。"""

from minicode_lite.config import RuntimeConfig
from minicode_lite.mock_model import MockModelAdapter
from minicode_lite.qwen_adapter import QwenModelAdapter
from minicode_lite.tooling import ToolRegistry
from minicode_lite.types import ModelAdapter


def create_model_adapter(config: RuntimeConfig, tools: ToolRegistry) -> tuple[ModelAdapter, str]:
    """依据配置完整性创建模型适配器，并返回配置层已经生成的安全诊断信息。"""

    # 三项连接配置完整时，才把模型名、服务地址和密钥交给真实适配器发起后续请求。
    if config.is_qwen_configured:
        return (
            QwenModelAdapter(
                model=config.model,
                base_url=config.base_url,
                api_key=config.api_key,
                # 传入同一注册表，保证 provider 收到的工具定义与本轮实际执行的工具一致。
                tools=tools,
            ),
            # 配置层负责生成且已避免回显密钥的诊断；注册层只透传，不重新拼接敏感信息。
            config.diagnostic,
        )

    # 配置不完整并非程序错误；回退到 mock 让 CLI、教学演示和离线测试仍能完成最小闭环。
    return MockModelAdapter(), config.diagnostic
