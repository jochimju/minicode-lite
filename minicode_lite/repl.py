from __future__ import annotations

"""可测试的交互式 REPL 表面；不依赖 raw mode 或全屏终端。"""

from pathlib import Path
from typing import Any, Callable, Iterable, TextIO

from minicode_lite.agent_loop import run_agent_turn
from minicode_lite.cli_commands import try_handle_local_command
from minicode_lite.config import load_runtime_config
from minicode_lite.memory import MemoryManager
from minicode_lite.model_registry import create_model_adapter
from minicode_lite.permissions import PermissionManager
from minicode_lite.prompt import build_system_prompt
from minicode_lite.session import SessionData, create_new_session, save_session
from minicode_lite.skills import discover_skills
from minicode_lite.tools import create_default_tool_registry, create_load_skill_tool
from minicode_lite.types import ChatMessage
from minicode_lite.tui.input_handler import classify_input
from minicode_lite.tui.tool_lifecycle import ToolLifecycle


class Repl:
    """管理多轮消息、命令分流、可见 transcript 和 session 保存。"""

    def __init__(self, *, cwd: str | Path | None = None, input_fn: Callable[[str], str] = input,
                 output: TextIO | None = None, model_factory: Callable | None = None,
                 model: Any | None = None) -> None:
        import sys
        # 工作区是文件工具、权限、memory 和 session 的共同安全边界，整个 REPL 生命周期保持不变。
        self.cwd = Path.cwd() if cwd is None else Path(cwd)
        # 输入函数和输出流可注入，测试因此不需要真的占用终端或模拟键盘。
        self.input_fn = input_fn
        self.output = sys.stdout if output is None else output
        # 每个 REPL 实例持有独立注册表，避免并行测试或多个界面之间共享可变工具状态。
        self.tools = create_default_tool_registry()
        self.tools.register(create_load_skill_tool(str(self.cwd)))
        # 权限、memory 和 session 都绑定同一个 workspace，防止交互命令跨项目读取状态。
        self.permissions = PermissionManager(self.cwd)
        self.memory = MemoryManager(self.cwd)
        self.session: SessionData = create_new_session(self.cwd)
        # messages 是模型消费的权威历史；transcript 是面向用户的生命周期投影，二者职责不同。
        self.messages: list[ChatMessage] = []
        self.transcript = ToolLifecycle()
        # 工厂供正常运行使用，直接 model 注入供离线测试和教学演示使用。
        self.model_factory = model_factory or create_model_adapter
        self._model = model

    def _ensure_model(self, user_prompt: str) -> Any:
        """首次 agent 输入时延迟创建模型和 system prompt，后续轮次复用同一状态。"""

        if not self.messages:
            # 注入模型时无需读取 provider 配置；正常入口则在真正需要推理时才加载配置。
            model = self._model
            if model is None:
                config = load_runtime_config()
                model, _ = self.model_factory(config, self.tools)
            # 技能摘要和相关 memory 只进入 system prompt，不混入用户原始输入。
            skills = discover_skills(self.cwd)
            self.messages.append({"role": "system", "content": build_system_prompt(
                cwd=str(self.cwd), tools=self.tools, permissions=self.permissions,
                memory_context=self.memory.get_context(user_prompt), skills=skills or None,
            )})
            self._model = model
        return self._model

    def handle(self, text: str) -> bool:
        """处理一行输入；返回 False 表示请求退出。"""
        # 主循环只消费结构化事件，不重复实现斜杠和空白字符串判断。
        event = classify_input(text)
        if event.kind == "exit":
            # False 是显式循环控制信号，退出命令不会被写入模型消息或 session。
            return False
        if event.kind == "empty":
            # 空行是无副作用操作，保持 REPL 可继续接收下一行。
            return True
        if event.kind == "local":
            # 本地命令优先执行，因此缺少 API key 时仍可查看 tools、session 和 readiness。
            result = try_handle_local_command(event.text, tools=self.tools, cwd=self.cwd,
                                              permissions=self.permissions, session=self.session)
            if result is None:
                # 未知斜杠命令不能降级为模型 prompt，否则拼写错误会产生意外网络调用。
                print("Unknown local command. Try /tools or /exit.", file=self.output)
            else:
                print(result, file=self.output)
            return True
        # 普通任务首次触发模型初始化，并用当前任务检索相关项目 memory。
        model = self._ensure_model(event.text)
        # 用户消息先进入权威历史，再交给 agent loop 生成后续工具和 assistant 消息。
        self.messages.append({"role": "user", "content": event.text})
        self.transcript.entries.append(self._entry("user", event.text))
        # callback 只负责展示投影；工具执行和消息协议仍由 agent loop 统一维护。
        result = run_agent_turn(
            model=model, tools=self.tools, messages=self.messages, cwd=str(self.cwd),
            permissions=self.permissions, session=self.session,
            on_tool_start=lambda name, call: self._on_tool_start(name, call),
            on_tool_result=lambda name, output, error: self._on_tool_result(name, output, error),
            on_assistant_message=lambda content: self._on_assistant(content),
        )
        # loop 返回完整新历史，替换旧引用可避免遗漏中间 tool_result 或 progress 消息。
        self.messages = result
        self.session.messages = [dict(item) for item in result]
        # 每轮完成即保存，终端随后异常退出时也能回放最近一次完整 turn。
        save_session(self.session)
        return True

    def run(self, inputs: Iterable[str] | None = None) -> int:
        """运行可替换输入源的主循环，EOF 也按退出处理。"""
        # iterable 输入用于测试；真实运行则逐行调用 input_fn 并显示固定 prompt。
        source = iter(inputs) if inputs is not None else None
        while True:
            try:
                line = next(source) if source is not None else self.input_fn("minicode> ")
            except (StopIteration, EOFError):
                # 测试输入耗尽和终端 EOF 都采用同一条正常退出路径。
                break
            if not self.handle(line):
                break
        # 退出前清理展示层状态，避免 replay 永久保留误导性的 running 工具。
        dangling = self.transcript.finalize()
        if dangling:
            print(f"Warning: {dangling} tool call(s) ended without a result.", file=self.output)
        # 即使从未进入 agent turn，也保存当前 session，使本地命令产生的 checkpoint 状态不丢失。
        save_session(self.session)
        return 0

    def _entry(self, kind: str, body: str):
        """创建普通 transcript 事件，集中保持展示对象构造方式一致。"""

        from minicode_lite.tui.tool_lifecycle import TranscriptEntry
        return TranscriptEntry(kind=kind, body=body)

    def _on_tool_start(self, name: str, call: Any) -> None:
        """把 agent loop 的工具开始回调投影到 transcript 和终端。"""

        # 当前 ToolCall 是 TypedDict；兼容属性对象可让教学 fake 更容易注入。
        tool_id = getattr(call, "id", None) or (call.get("id") if isinstance(call, dict) else "unknown")
        self.transcript.start(name, str(tool_id), getattr(call, "input", None) or (call.get("input") if isinstance(call, dict) else None))
        print(f"[tool:start] {name}", file=self.output)

    def _on_tool_result(self, name: str, output: str, error: bool) -> None:
        """结束同名的当前工具，并显示成功或错误状态。"""

        # agent loop 当前按顺序执行工具，回调未携带 ID，因此用正在运行的同名事件完成配对。
        running = next((item for item in self.transcript.running if item.tool_name == name), None)
        self.transcript.result(name, running.tool_use_id if running else "unknown", output, error)
        print(f"[tool:{'error' if error else 'result'}] {output}", file=self.output)

    def _on_assistant(self, content: str) -> None:
        """记录并显示最终 assistant 文本。"""

        self.transcript.entries.append(self._entry("assistant", content))
        print(content, file=self.output)


def run_repl(*, cwd: str | Path | None = None, inputs: Iterable[str] | None = None,
             input_fn: Callable[[str], str] = input, output: TextIO | None = None) -> int:
    """REPL 的函数式入口，方便 console script 和自动化测试复用。"""
    # 保持 console script 入口足够薄，所有可测试状态都集中在 Repl 对象内。
    return Repl(cwd=cwd, input_fn=input_fn, output=output).run(inputs)
