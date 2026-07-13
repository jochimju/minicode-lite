from __future__ import annotations

"""将本地 harness 消息与工具协议转换为 Qwen/OpenAI-compatible Chat Completions 请求。"""

import json
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from minicode_lite.tooling import ToolRegistry
from minicode_lite.types import AgentStep, ChatMessage


# transport 保持为可注入函数，让协议转换可在不访问网络的条件下被测试。
Transport = Callable[[str, dict[str, str], dict[str, Any]], dict[str, Any]]


def _serialize_tools(tools: ToolRegistry) -> list[dict[str, Any]]:
    """把本地工具定义映射成 Chat Completions 规定的 function 工具结构。"""

    # 注册表的稳定顺序也成为传给模型的工具顺序，便于测试与提示词调试。
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            },
        }
        for tool in tools.list()
    ]


def _serialize_tool_call(message: ChatMessage) -> dict[str, Any]:
    """将本地单个工具调用记录编码为 provider 侧 tool_calls 数组的一个元素。"""

    # ID 与名称是工具结果关联和注册表查找的稳定键，缺失时不能构造可恢复的请求。
    tool_use_id = message.get("toolUseId")
    tool_name = message.get("toolName")
    if not isinstance(tool_use_id, str) or not tool_use_id:
        raise RuntimeError("Cannot serialize assistant tool call without a non-empty toolUseId.")
    if not isinstance(tool_name, str) or not tool_name:
        raise RuntimeError("Cannot serialize assistant tool call without a non-empty toolName.")

    try:
        # 紧凑 JSON 使测试和日志保持稳定，同时 provider 仍收到标准 JSON 参数字符串。
        arguments = json.dumps(message.get("input"), ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as error:
        # 参数无法编码意味着本地历史本身不符合 provider 协议，应在发请求前明确失败。
        raise RuntimeError("Cannot serialize assistant tool call arguments as JSON.") from error

    return {
        "id": tool_use_id,
        "type": "function",
        "function": {"name": tool_name, "arguments": arguments},
    }


def _serialize_tool_result(message: ChatMessage) -> dict[str, Any]:
    """将本地工具观察结果关联回 provider 要求的 tool_call_id。"""

    # 结果没有对应调用 ID 时，provider 无法将观察值归属给正确的工具调用。
    tool_use_id = message.get("toolUseId")
    if not isinstance(tool_use_id, str) or not tool_use_id:
        raise RuntimeError("Cannot serialize tool result without a non-empty toolUseId.")

    return {
        "role": "tool",
        "tool_call_id": tool_use_id,
        "content": message.get("content", ""),
    }


def _serialize_messages(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    """转换 harness 历史，并拒绝当前 provider 协议没有定义的本地角色。"""

    serialized: list[dict[str, Any]] = []
    message_index = 0
    while message_index < len(messages):
        message = messages[message_index]
        # 普通消息可直接复用 role/content；progress 没有独立 provider 角色，因此降级为 assistant 文本。
        role = message.get("role")
        if role in {"system", "user", "assistant", "assistant_progress"}:
            provider_role = "assistant" if role == "assistant_progress" else role
            serialized.append({"role": provider_role, "content": message.get("content", "")})
            message_index += 1
            continue
        if role == "assistant_tool_call":
            # 本地逐条保存调用以配对结果，发送时再还原成 provider 所需的一个调用批次。
            tool_calls: list[dict[str, Any]] = []
            assistant_content = message.get("content", "")
            while (
                message_index < len(messages)
                and messages[message_index].get("role") == "assistant_tool_call"
            ):
                tool_calls.append(_serialize_tool_call(messages[message_index]))
                message_index += 1
            serialized.append(
                {
                    "role": "assistant",
                    "content": assistant_content,
                    "tool_calls": tool_calls,
                }
            )
            continue
        if role == "tool_result":
            # 运行结果必须以 tool 角色返回，供 provider 将其交给后续模型步骤。
            serialized.append(_serialize_tool_result(message))
            message_index += 1
            continue
        # 未知角色没有可靠的 provider 语义，避免静默丢失或错误篡改历史。
        raise RuntimeError(f"Cannot serialize unsupported local message role: {role!r}.")
    return serialized


class _NoRedirectHandler(HTTPRedirectHandler):
    """拒绝 HTTP 重定向，避免认证头被自动转发给重定向目标。"""

    def http_error_302(
        self,
        request: Request,
        response: Any,
        code: int,
        message: str,
        headers: Any,
    ) -> Any:
        # 重定向会改变请求目标；Authorization 只对原始 endpoint 有授权意义，
        # 因此把 3xx 当作普通 HTTP 失败交给 transport 的统一错误边界处理。
        raise HTTPError(request.full_url, code, message, headers, response)

    # urllib 将这些状态码都路由到重定向 handler，统一拒绝可覆盖跨主机和同主机跳转。
    http_error_301 = http_error_302
    http_error_303 = http_error_302
    http_error_307 = http_error_302
    http_error_308 = http_error_302


def _default_transport(
    endpoint: str, headers: dict[str, str], payload: dict[str, Any]
) -> dict[str, Any]:
    """使用 urllib 发起 UTF-8 JSON POST，并把底层通信错误收束为安全错误。"""

    try:
        # 请求体在创建 Request 前完成编码，保证传输层只处理字节数据。
        request_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError) as error:
        # 不回显 payload，防止以后其中加入敏感运行时信息时被异常文本泄露。
        raise RuntimeError("Cannot serialize Qwen-compatible request payload.") from error

    # 显式指定 POST 与传入的认证头，避免依赖 urllib 对带 data 请求的隐式行为。
    request = Request(endpoint, data=request_body, headers=headers, method="POST")
    try:
        # 上下文管理器负责及时关闭连接，timeout 防止网络问题无限阻塞 agent loop。
        # 独立 opener 明确安装禁止重定向的 handler，避免全局默认策略
        # 把 Authorization 自动带往 Location 指向的未知目标。
        opener = build_opener(_NoRedirectHandler())
        with opener.open(request, timeout=60) as response:
            response_body = response.read()
    except HTTPError as error:
        # HTTP 状态足以指导调用方处理，响应体可能包含服务端回显的敏感内容，因此不输出。
        raise RuntimeError(
            f"Qwen-compatible request failed with HTTP status {error.code}."
        ) from error
    except (URLError, OSError) as error:
        # 网络异常不包含请求头或 URL 参数，统一文字可避免意外泄露 API key。
        raise RuntimeError("Qwen-compatible request failed due to a network error.") from error

    try:
        # provider 的成功响应必须是 UTF-8 编码的 JSON 对象，数组或纯文本都不满足协议。
        decoded_response = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("Qwen-compatible response body is not valid JSON.") from error
    if not isinstance(decoded_response, dict):
        raise RuntimeError("Qwen-compatible response body must be a JSON object.")
    return decoded_response


def _parse_tool_calls(raw_tool_calls: Any) -> list[dict[str, Any]]:
    """校验 provider 工具调用并还原为 agent loop 可执行的 ToolCall 字典。"""

    # 空列表没有可执行动作，不能伪装成一次合法 tool_calls 步骤。
    if not isinstance(raw_tool_calls, list) or not raw_tool_calls:
        raise RuntimeError("Invalid Qwen-compatible response: tool_calls must be a non-empty list.")

    calls: list[dict[str, Any]] = []
    for raw_call in raw_tool_calls:
        # 每个元素及其 function 部分都必须是对象，才能安全读取固定字段。
        if not isinstance(raw_call, dict) or not isinstance(raw_call.get("function"), dict):
            raise RuntimeError("Invalid Qwen-compatible response: malformed tool call.")
        call_id = raw_call.get("id")
        function = raw_call["function"]
        tool_name = function.get("name")
        raw_arguments = function.get("arguments")
        # 当前 harness 仅能执行 function 调用，其他 provider 扩展类型不能被错误地当作本地工具。
        if raw_call.get("type") != "function":
            raise RuntimeError(
                "Invalid Qwen-compatible response: tool call type must be 'function'."
            )
        if not isinstance(call_id, str) or not call_id:
            raise RuntimeError("Invalid Qwen-compatible response: tool call id is missing.")
        if not isinstance(tool_name, str) or not tool_name:
            raise RuntimeError("Invalid Qwen-compatible response: tool name is missing.")
        if not isinstance(raw_arguments, str):
            raise RuntimeError("Invalid Qwen-compatible response: tool arguments must be JSON text.")
        try:
            # API 的 arguments 是 JSON 字符串；解析后只接受对象，以匹配本地工具参数约定。
            arguments = json.loads(raw_arguments)
        except json.JSONDecodeError as error:
            raise RuntimeError("Invalid Qwen-compatible response: tool arguments are not valid JSON.") from error
        if not isinstance(arguments, dict):
            raise RuntimeError("Invalid Qwen-compatible response: tool arguments must be a JSON object.")
        calls.append({"id": call_id, "toolName": tool_name, "input": arguments})
    return calls


def _parse_response(response: dict[str, Any]) -> AgentStep:
    """从 Chat Completions 成功响应取出文本回答或工具调用步骤。"""

    # 只消费第一候选项，与最小 agent loop 的“一次请求对应一步”模型保持一致。
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise RuntimeError("Invalid Qwen-compatible response: choices[0] is missing.")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise RuntimeError("Invalid Qwen-compatible response: choices[0].message is missing.")

    # 工具调用优先，避免 provider 附带的说明文本让 agent loop 跳过必须执行的行动。
    if "tool_calls" in message:
        return AgentStep(type="tool_calls", calls=_parse_tool_calls(message["tool_calls"]))
    # 没有工具调用时，非空文本才是当前步骤的最终 assistant 回答。
    content = message.get("content")
    if isinstance(content, str) and content:
        return AgentStep(type="assistant", content=content)
    raise RuntimeError("Invalid Qwen-compatible response: message has no text or tool calls.")


class QwenModelAdapter:
    """适配 Qwen 与其他 OpenAI-compatible Chat Completions 服务到 ModelAdapter 协议。"""

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: str,
        tools: ToolRegistry,
        transport: Transport | None = None,
    ) -> None:
        # 配置保持原样保存，唯一的 URL 规范化在请求时集中完成。
        self._model = model
        self._base_url = base_url
        self._api_key = api_key
        self._tools = tools
        # 默认传输是真实网络实现，测试可注入纯内存替身观察准确请求内容。
        self._transport = transport or _default_transport

    def next(
        self,
        messages: list[ChatMessage],
        on_stream_chunk: Callable[[str], None] | None = None,
        store: Any | None = None,
    ) -> AgentStep:
        """发送一次非流式请求，并把 provider 响应收束为 AgentStep。"""

        # 流式回调与运行时存储已在统一协议中预留，本阶段尚未把它们传给 provider。
        del on_stream_chunk, store
        # 无论配置末尾是否已有斜杠，端点始终且只会以 /chat/completions 结尾一次。
        endpoint = f"{self._base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": _serialize_messages(messages),
            "tools": _serialize_tools(self._tools),
        }
        try:
            # 传输边界只接收无敏感内容的统一错误，调用方不需要理解 urllib 的异常层级。
            response = self._transport(endpoint, headers, payload)
        except (KeyboardInterrupt, SystemExit):
            # 进程级中断必须保留原语义，不能被包装成可恢复的模型错误。
            raise
        except RuntimeError:
            # 默认传输已经生成安全、可读的 RuntimeError，保持其具体 HTTP/网络信息。
            raise
        except Exception as error:  # noqa: BLE001
            # 注入传输也不能把认证头或完整请求带到用户可见的异常文本中。
            raise RuntimeError("Qwen-compatible request failed.") from error
        if not isinstance(response, dict):
            raise RuntimeError("Invalid Qwen-compatible response: expected a JSON object.")
        return _parse_response(response)
