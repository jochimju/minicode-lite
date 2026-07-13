from __future__ import annotations

# 提供运行时模型配置的统一读取入口；配置缺失时保留 mock model 的可用路径，而不是中断程序。

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_ENVIRONMENT_KEYS = {
    "model": "MINI_CODE_MODEL",
    "base_url": "CUSTOM_API_BASE_URL",
    "api_key": "CUSTOM_API_KEY",
}


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    """保存 Qwen 适配器需要的最小配置，以及可直接展示的非敏感诊断信息。"""

    # model 决定兼容接口应调用的具体模型，空字符串表示尚未配置。
    model: str
    # base_url 是兼容接口地址，加载时会统一移除末尾斜杠以避免后续拼接出双斜杠。
    base_url: str
    # api_key 只在内存中传递给后续适配器，诊断信息绝不能回显其内容。
    api_key: str
    # diagnostic 说明当前是否可启用真实模型，供 CLI 或 headless 层决定是否提示用户。
    diagnostic: str

    @property
    def is_qwen_configured(self) -> bool:
        """仅当模型名、接口地址和密钥都非空时，才允许切换到真实 Qwen 适配器。"""

        # 三项缺一不可；使用 bool 明确把空字符串归为“未配置”，避免运行时再得到不清晰的 provider 错误。
        return bool(self.model and self.base_url and self.api_key)


def _load_dotenv_values(path: Path) -> dict[str, str]:
    """读取简单的 KEY=value 文件；该函数只返回数据，绝不修改进程环境变量。"""

    # 缺少本地 .env 是常规状态，返回空映射让调用方继续尝试 JSON 或生成未配置诊断。
    if not path.is_file():
        return {}

    # 使用 UTF-8 读取可使示例文件与不同开发环境保持一致；读取结果只存在当前函数局部变量中。
    lines = path.read_text(encoding="utf-8").splitlines()
    # 单独保存解析结果，避免调用 dotenv 类库时产生将密钥写入 os.environ 的副作用。
    values: dict[str, str] = {}
    for raw_line in lines:
        # 去除行首尾空白后再判断，既支持空行也支持缩进的注释行。
        line = raw_line.strip()
        if not line or line.startswith("#"):
            # 注释与空行不携带配置，因此直接跳过并处理下一行。
            continue
        # 只接受带等号的简单赋值格式；其他行不是本项目支持的 .env 语法。
        key, separator, value = line.partition("=")
        if not separator:
            # 无法形成键值对的行不影响其余有效配置，保持加载器的容错性。
            continue
        # 去除键和值的外围空白，同时保留空值以表达“该来源明确未配置此项”。
        values[key.strip()] = value.strip()
    return values


def _load_settings_values(path: Path | None) -> dict[str, str]:
    """读取可选 JSON 设置文件，并将允许的逻辑键转换为字符串值。"""

    # 未提供设置路径或文件不存在都代表没有最低优先级配置，而不是配置错误。
    if path is None or not path.is_file():
        return {}

    try:
        # JSON 只作为本地设置输入，解析后仍须检查顶层是否是对象。
        raw_settings: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        # 不附带原始内容或密钥，向调用者提供足以定位问题的稳定异常类型和信息。
        raise ValueError("Runtime settings JSON is malformed.") from error

    if not isinstance(raw_settings, dict):
        # 数组等 JSON 值没有命名字段，无法承载 model、base_url 与 api_key 配置。
        raise ValueError("Runtime settings JSON must be an object.")

    # 仅拷贝本模块约定的逻辑键，避免把设置文件中不相关的数据意外扩散到运行时配置。
    return {
        name: value
        for name in _ENVIRONMENT_KEYS
        if isinstance(value := raw_settings.get(name), str)
    }


def _value_by_precedence(
    *, environment_name: str, logical_name: str, dotenv_values: dict[str, str], settings_values: dict[str, str]
) -> str:
    """按照环境变量、.env、JSON 的顺序取得一个字段，并把纯空白统一视为未配置。"""

    # “存在”与“非空”分开处理，使用户可以用空环境变量或空 .env 值显式保持 mock 模式。
    if environment_name in os.environ:
        # 环境变量优先级最高；先取原始值，统一在分支结束后清理空白。
        value = os.environ[environment_name]
    elif environment_name in dotenv_values:
        # .env 中存在同名键时优先于 JSON，即使其值为空也符合来源优先级约定。
        value = dotenv_values[environment_name]
    else:
        # JSON 使用对外暴露的逻辑键，因此只在前两个来源都缺少该字段时查询它。
        value = settings_values.get(logical_name, "")
    # 所有来源在同一边界去除首尾空白，确保空白字符串不会绕过完整性检查或误导诊断。
    return value.strip()


def _configuration_diagnostic(config: RuntimeConfig) -> str:
    """生成不含密钥值的可操作诊断，说明真实模型是否已经具备启动条件。"""

    # 完整配置只需给出状态；不回显任何配置值可避免地址和密钥进入日志。
    if config.is_qwen_configured:
        return "Qwen runtime configuration is complete."

    # 逐项检查实际值，将缺失原因映射回用户需要设置的环境变量名称。
    missing = [
        environment_name
        for logical_name, environment_name in _ENVIRONMENT_KEYS.items()
        if not getattr(config, logical_name)
    ]
    # 只列出变量名而非变量值，让诊断既能指导配置又不会泄露 API key。
    return "Qwen runtime configuration is incomplete; missing: " + ", ".join(missing) + "."


def load_runtime_config(
    *, settings_path: Path | None = None, dotenv_path: Path | None = None
) -> RuntimeConfig:
    """加载真实模型配置；默认读取当前目录 .env，缺项时返回可供 mock 路径使用的未配置状态。"""

    # 未显式传入 .env 路径时遵循项目本地约定，在当前工作目录寻找 .env 文件。
    effective_dotenv_path = dotenv_path if dotenv_path is not None else Path(".env")
    # 两种文件输入先独立读取，便于后续按每个字段执行统一的来源优先级规则。
    dotenv_values = _load_dotenv_values(effective_dotenv_path)
    settings_values = _load_settings_values(settings_path)
    # 分别解析每个字段，避免一个来源缺少单项时阻塞其余字段从低优先级来源回退。
    model = _value_by_precedence(
        environment_name=_ENVIRONMENT_KEYS["model"],
        logical_name="model",
        dotenv_values=dotenv_values,
        settings_values=settings_values,
    )
    base_url = _value_by_precedence(
        environment_name=_ENVIRONMENT_KEYS["base_url"],
        logical_name="base_url",
        dotenv_values=dotenv_values,
        settings_values=settings_values,
    ).rstrip("/")
    api_key = _value_by_precedence(
        environment_name=_ENVIRONMENT_KEYS["api_key"],
        logical_name="api_key",
        dotenv_values=dotenv_values,
        settings_values=settings_values,
    )
    # 先构造无诊断的不可变配置，以便复用同一套完整性判定生成诊断文本。
    provisional_config = RuntimeConfig(model=model, base_url=base_url, api_key=api_key, diagnostic="")
    # 返回最终对象时将诊断固化，调用方无需再次读取文件或接触密钥即可知道是否可启用真实模型。
    return RuntimeConfig(
        model=model,
        base_url=base_url,
        api_key=api_key,
        diagnostic=_configuration_diagnostic(provisional_config),
    )
