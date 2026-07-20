from __future__ import annotations

"""检查 MiniCode Lite 本地运行条件，并生成稳定的文本或 JSON 诊断。"""

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from minicode_lite.config import RuntimeConfig, load_runtime_config
from minicode_lite.tooling import ToolRegistry


# schema 版本只在字段契约发生不兼容变化时升级，方便脚本安全消费 JSON。
READINESS_SCHEMA_VERSION = "1.0"
# pyproject.toml 当前声明 Python >= 3.11；检查逻辑与安装边界保持同一来源语义。
MINIMUM_PYTHON = (3, 11)


@dataclass(frozen=True, slots=True)
class ReadinessCheck:
    """描述一个独立的本地检查及其可操作结论。"""

    # name 是 JSON 消费方可依赖的稳定标识，不使用易变化的展示文本作键。
    name: str
    # status 只取 pass、warning、blocked，便于汇总时按严重程度归并。
    status: str
    # summary 不包含凭据值，只解释事实和下一步动作。
    summary: str


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    """汇总一次只读预检；该对象不发起真实 provider 请求。"""

    schema_version: str
    status: str
    mode: str
    cwd: str
    python_version: str
    checks: tuple[ReadinessCheck, ...]

    def to_dict(self) -> dict[str, object]:
        """转成只含 JSON 原生类型的稳定负载。"""

        # 显式把 tuple 转成 list，保证函数返回值本身就是 JSON schema 所声明的数组类型。
        payload = asdict(self)
        payload["checks"] = [asdict(check) for check in self.checks]
        return payload


def _python_check() -> ReadinessCheck:
    """验证解释器版本是否满足项目安装下限。"""

    current = sys.version_info[:2]
    required = ".".join(str(part) for part in MINIMUM_PYTHON)
    if current >= MINIMUM_PYTHON:
        return ReadinessCheck("python", "pass", f"Python {sys.version.split()[0]} meets >= {required}.")
    return ReadinessCheck("python", "blocked", f"Python >= {required} is required.")


def _workspace_check(workspace: Path) -> ReadinessCheck:
    """确认 cwd 是存在且可读取的目录，避免后续工具在错误根路径上工作。"""

    if not workspace.exists():
        return ReadinessCheck("cwd", "blocked", "Workspace does not exist.")
    if not workspace.is_dir():
        return ReadinessCheck("cwd", "blocked", "Workspace is not a directory.")
    try:
        # 读取一次目录项即可验证最小访问能力；不递归扫描，也不修改工作区。
        next(workspace.iterdir(), None)
    except OSError:
        return ReadinessCheck("cwd", "blocked", "Workspace cannot be read.")
    return ReadinessCheck("cwd", "pass", "Workspace exists and is readable.")


def _tools_check(tools: ToolRegistry) -> ReadinessCheck:
    """确认 agent 至少拥有一个已注册工具。"""

    count = len(tools.list())
    if count == 0:
        return ReadinessCheck("tools", "blocked", "No tools are registered.")
    return ReadinessCheck("tools", "pass", f"{count} tool(s) registered.")


def _model_check(config: RuntimeConfig) -> tuple[ReadinessCheck, str]:
    """区分真实 Qwen 就绪与 mock fallback 就绪，不进行联网探测。"""

    if config.is_qwen_configured:
        return ReadinessCheck("model", "pass", "Qwen configuration is complete; live connectivity was not tested."), "qwen"
    # 缺真实凭据不会阻断教学闭环，因为 model_registry 会确定性回退到 mock。
    return ReadinessCheck("model", "warning", f"{config.diagnostic} Mock fallback is ready."), "mock"


def build_readiness_report(
    cwd: str | Path,
    tools: ToolRegistry,
    *,
    config: RuntimeConfig | None = None,
) -> ReadinessReport:
    """执行本地只读检查，并按 blocked > warning > ready 汇总状态。"""

    workspace = Path(cwd).resolve()
    # 显式 config 便于测试隔离；默认只读取目标 workspace 自己的 .env。
    runtime_config = config or load_runtime_config(dotenv_path=workspace / ".env")
    model_check, mode = _model_check(runtime_config)
    checks = (_python_check(), _workspace_check(workspace), _tools_check(tools), model_check)
    statuses = {check.status for check in checks}
    if "blocked" in statuses:
        status = "blocked"
    elif "warning" in statuses:
        status = "warning"
    else:
        status = "ready"
    return ReadinessReport(
        schema_version=READINESS_SCHEMA_VERSION,
        status=status,
        mode=mode,
        cwd=str(workspace),
        python_version=sys.version.split()[0],
        checks=checks,
    )


def format_readiness_text(report: ReadinessReport) -> str:
    """把报告格式化为适合终端阅读的稳定文本。"""

    lines = [f"Readiness: {report.status}", f"Mode: {report.mode}", f"Workspace: {report.cwd}"]
    lines.extend(f"- {check.name}: {check.status} - {check.summary}" for check in report.checks)
    return "\n".join(lines)


def format_readiness_json(report: ReadinessReport) -> str:
    """输出可由 CI 和后续 release gate 消费的确定性 JSON。"""

    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)


__all__ = [
    "READINESS_SCHEMA_VERSION",
    "ReadinessCheck",
    "ReadinessReport",
    "build_readiness_report",
    "format_readiness_json",
    "format_readiness_text",
]
