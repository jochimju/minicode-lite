from __future__ import annotations

# 定义 MiniCode Lite 各层之间传递数据时共同遵守的类型契约。

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, TypedDict


class ChatMessage(TypedDict, total=False): #继承自 TypedDict  total=False 表示：下面声明的所有字段都是可选的。
    """一条对话历史记录；不同角色只会使用与自己相关的字段。"""

    # role 决定这条记录由谁产生，以及 agent loop 应如何解释其余字段。
    role: Literal[ #Literal 表示值只能是列出的几个固定字面量。
        "system", #系统提示
        "user", #用户消息
        "assistant", #模型最终回答
        "assistant_progress", #模型过程性进度消息
        "assistant_tool_call", #模型请求调用工具
        "tool_result", #工具执行结果
    ]
    # 普通消息、最终回答和工具执行结果都通过 content 保存文本内容。
    content: str
    # 工具调用和工具结果用同一个 ID 配对，便于模型追踪一次调用的来龙去脉。
    toolUseId: str
    # 记录工具名，避免消费者需要重新从上下文推断调用的是哪个工具。
    toolName: str
    # assistant_tool_call 角色用 input 保存模型传给工具的结构化参数。
    input: Any #Any 表示任意类型。
    # tool_result 角色用 isError 表明本次工具运行是否失败。
    isError: bool


class ToolCall(TypedDict):
    """模型请求执行一次工具时使用的最小描述。"""

    # ID 会原样写入后续的 assistant_tool_call 和 tool_result 消息。
    id: str
    # 工具注册表依靠名称查找对应的 ToolDefinition。
    toolName: str
    # 参数保持通用类型，由具体工具的 validator 负责收窄和校验。
    input: Any

#@dataclass是一个装饰器。它会根据类中的字段，自动生成一些常用方法，例如：__init__()：初始化对象 __repr__()：方便打印对象
#slots=True 表示这个数据类只允许声明过的字段，通常不能随意添加新属性。
@dataclass(slots=True)
class StepDiagnostics:
    """保存模型步骤的可选诊断信息，当前最小 loop 只负责透传。"""

    # stopReason 说明 provider 或策略为何停止生成；缺失时表示没有附加诊断。
    stopReason: str | None = None
    # blockTypes 记录本步骤中实际出现的内容块种类。
    blockTypes: list[str] = field(default_factory=list) #field(...)如果调用者没有提供 blockTypes，就为这个对象创建一个新的空列表。
    # ignoredBlockTypes 记录被上层主动忽略的内容块，方便日后排查。
    ignoredBlockTypes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AgentStep:
    """模型一次输出的统一表示：最终/进度文本，或一组工具调用。"""

    # type 是 agent loop 的主分支开关：文本回答或工具调用。
    type: Literal["assistant", "tool_calls"]
    # assistant 步骤的文本内容；工具调用步骤通常保留为空字符串。
    content: str = ""
    # kind 区分最终回答与仅供展示、不终止循环的进度消息。
    kind: Literal["final", "progress"] | None = None
    # calls 包含模型要求按顺序执行的工具调用。
    calls: list[ToolCall] = field(default_factory=list)
    # 兼容另一种表示进度消息的字段，便于适配器逐步演进。
    contentKind: Literal["progress"] | None = None
    # diagnostics 保留 provider 诊断信息，不强迫最小实现依赖它。
    diagnostics: StepDiagnostics | None = None

#Protocol 来自 typing，用于定义接口。 只要一个对象拥有规定的方法和方法签名，就可以被当作 ModelAdapter 使用。
class ModelAdapter(Protocol):
    """约束所有模型适配器都能根据消息历史产出一个 AgentStep。"""

    def next(
        self, #self：当前对象本身
        # 传入副本，避免模型实现意外改写 agent loop 正在维护的历史。
        messages: list[ChatMessage],
        # 流式回调预留给真实 provider；当前 mock 模型可忽略它。
        on_stream_chunk: Callable[[str], None] | None = None,
        # store 为以后接入会话、缓存或运行时状态保留的扩展点。
        store: Any | None = None,
        # 返回值必须已经被适配器标准化，loop 不需要了解 provider 原始格式。
    ) -> AgentStep: ...
