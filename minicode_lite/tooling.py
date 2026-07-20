from __future__ import annotations

# 提供工具注册、查找、输入校验和异常隔离这一层 harness 基础设施。

from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from minicode_lite.logging_config import log_tool_execution, monotonic_milliseconds


@dataclass(slots=True)
class ToolResult:
    """工具执行后的统一结果；失败也返回对象，而不是让 agent loop 崩溃。"""

    # ok 让调用方无需解析文本即可判断工具是否成功。
    ok: bool
    # output 是要写回对话历史并提供给模型阅读的用户可见文本。
    output: str


@dataclass(slots=True)
class ToolContext:
    """每次工具执行都携带的运行环境，而非让工具直接依赖全局状态。"""

    # cwd 是所有相对路径工具的工作区根目录。
    cwd: str
    # permissions 预留给后续阶段的访问策略实现。
    permissions: Any | None = None
    # session 预留给会话持久化与回放功能。
    session: Any | None = None
    # runtime 存放本轮运行时共享的可选信息。
    runtime: dict[str, Any] | None = None


# Validator 接收原始模型输入，返回被校验和规范化后的工具参数。
Validator = Callable[[Any], Any]
# Runner 接收规范化参数和上下文，并始终返回结构化 ToolResult。
Runner = Callable[[Any, ToolContext], ToolResult]


@dataclass(slots=True)
class ToolDefinition:
    """描述一个可被模型调用的工具及其验证、执行函数。"""

    # name 是模型 ToolCall 与注册表索引之间的稳定键。
    name: str
    # description 面向模型或 `/tools` 命令解释工具用途。
    description: str
    # input_schema 是给模型/外部界面展示的输入形状说明。
    input_schema: dict[str, Any]
    # validator 把不可信的原始输入变成 runner 可以安全使用的输入。
    validator: Validator
    # run 承载具体副作用，并由注册表统一兜底异常。
    run: Runner


class ToolRegistry:
    """维护可用工具，并把各种工具错误转换为对话可消费的结果。"""

    def __init__(self, tools: list[ToolDefinition]) -> None:
        # 保留注册顺序，供 `/tools` 等面向用户的列表稳定展示。
        self._tools = list(tools)
        # 名称索引让一次工具调用可以高效定位定义。
        self._tool_index = {tool.name: tool for tool in tools}

    def list(self) -> list[ToolDefinition]:
        """返回工具列表副本，避免调用方改写注册表内部顺序。"""

        return list(self._tools)

    def find(self, name: str) -> ToolDefinition | None:
        """按 ToolCall 中的名称查找工具；找不到时显式返回 None。"""

        return self._tool_index.get(name)

    def execute(self, tool_name: str, input_data: Any, context: ToolContext) -> ToolResult:
        """执行一次工具调用，并把预期失败和意外异常都变为 ToolResult。"""

        # 从统一边界计时，未知工具、校验失败和 runner 异常都应留下同形日志。
        started_at = perf_counter()
        # 先查找，未知工具是模型可恢复的错误，不应中断整个 turn。
        tool = self.find(tool_name)
        if tool is None:
            result = ToolResult(ok=False, output=f"Unknown tool: {tool_name}")
        else:
            try:
                # 只有通过 validator 的数据才会交给真正有副作用的 runner。
                parsed = tool.validator(input_data)
            except (KeyError, TypeError, ValueError) as error:
                # 输入格式错误同样写成工具结果，让模型能据此修正下一步调用。
                result = ToolResult(ok=False, output=f"Input validation error in {tool_name}: {error}")
            else:
                try:
                    # 具体工具负责自己的业务行为，注册表负责统一的调用边界。
                    result = tool.run(parsed, context)
                except (KeyboardInterrupt, SystemExit):
                    # 用户中断和进程退出必须保持原语义，不能被伪装成普通工具错误。
                    raise
                except Exception as error:  # noqa: BLE001
                    # 未预期异常不能击穿 agent loop，转换后模型仍可收到失败原因。
                    result = ToolResult(ok=False, output=f"Tool {tool_name} crashed: {error}")
        # 日志只记录边界元数据；工具参数和输出可能含有用户源码或密钥，不能写入日志。
        log_tool_execution(
            tool_name,
            success=result.ok,
            duration_ms=monotonic_milliseconds(started_at),
        )
        return result
