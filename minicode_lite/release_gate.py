from __future__ import annotations

"""把编译、导入、测试和离线 smoke 组合成一个可重复执行的最小发布门禁。"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TextIO


RELEASE_GATE_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class ReleaseCheck:
    """记录单项门禁的稳定名称、结论和便于排障的有限输出。"""

    name: str
    status: str
    summary: str


@dataclass(frozen=True, slots=True)
class ReleaseReport:
    """汇总一次发布检查；只要任意检查失败，整体就不能通过。"""

    schema_version: str
    status: str
    cwd: str
    checks: tuple[ReleaseCheck, ...]

    def to_dict(self) -> dict[str, object]:
        """转换为仅含 JSON 原生类型的稳定机器接口。"""

        payload = asdict(self)
        # tuple 在 Python 内适合表达不可变快照，对外则必须转换为 JSON 数组。
        payload["checks"] = [asdict(check) for check in self.checks]
        return payload


def _limited_output(completed: subprocess.CompletedProcess[str]) -> str:
    """保留最后一小段命令输出，既支持排障，也避免报告无限膨胀。"""

    combined = "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part.strip())
    return combined[-1000:] if combined else "completed without output"


def _run_process(
    name: str,
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
) -> tuple[ReleaseCheck, subprocess.CompletedProcess[str]]:
    """执行一个不经过 shell 的子进程，并把退出码统一解释为门禁结果。"""

    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as error:
        # 启动失败和命令返回非零都属于门禁失败，但启动失败没有 CompletedProcess 可供后续解析。
        completed = subprocess.CompletedProcess(command, 127, "", str(error))
    status = "pass" if completed.returncode == 0 else "fail"
    return ReleaseCheck(name, status, _limited_output(completed)), completed


def run_release_gate(cwd: str | Path) -> ReleaseReport:
    """在目标仓库运行完整离线门禁，并对 readiness JSON 与 headless 输出做语义校验。"""

    workspace = Path(cwd).resolve()
    env = os.environ.copy()
    # 发布门禁必须可离线重复，显式清空 provider 配置，防止开发机的 .env 导致意外联网或计费。
    env.update(
        {
            "MINI_CODE_MODEL": "",
            "CUSTOM_API_BASE_URL": "",
            "CUSTOM_API_KEY": "",
            "PYTHONUTF8": "1",
        }
    )
    python = sys.executable
    checks: list[ReleaseCheck] = []

    check, _ = _run_process(
        "compile",
        [python, "-m", "compileall", "-q", "minicode_lite"],
        cwd=workspace,
        env=env,
    )
    checks.append(check)
    check, _ = _run_process(
        "import",
        [python, "-c", "import minicode_lite; import minicode_lite.headless"],
        cwd=workspace,
        env=env,
    )
    checks.append(check)
    check, _ = _run_process(
        "pytest",
        [python, "-m", "pytest", "-q"],
        cwd=workspace,
        env=env,
    )
    checks.append(check)

    with tempfile.TemporaryDirectory(prefix="minicode-lite-release-") as sessions_dir:
        # headless smoke 会保存 session；把它定向到临时目录，确保门禁不污染仓库或真实会话数据。
        smoke_env = dict(env)
        smoke_env["MINICODE_LITE_SESSIONS_DIR"] = sessions_dir
        readiness_check, readiness_process = _run_process(
            "readiness_json",
            [python, "-m", "minicode_lite", "/readiness", "--json"],
            cwd=workspace,
            env=smoke_env,
        )
        if readiness_check.status == "pass":
            try:
                payload = json.loads(readiness_process.stdout)
                valid = (
                    payload.get("schema_version") == "1.0"
                    and payload.get("status") in {"ready", "warning"}
                    and isinstance(payload.get("checks"), list)
                )
            except (json.JSONDecodeError, AttributeError):
                valid = False
            if not valid:
                readiness_check = ReleaseCheck(
                    "readiness_json", "fail", "readiness output does not match the expected schema"
                )
        checks.append(readiness_check)

        headless_check, headless_process = _run_process(
            "headless_smoke",
            [python, "-m", "minicode_lite", "release", "smoke"],
            cwd=workspace,
            env=smoke_env,
        )
        expected = "MiniCode Lite mock model received your message."
        if headless_check.status == "pass" and headless_process.stdout.strip() != expected:
            headless_check = ReleaseCheck(
                "headless_smoke", "fail", "headless smoke returned an unexpected response"
            )
        checks.append(headless_check)

    status = "pass" if all(check.status == "pass" for check in checks) else "fail"
    return ReleaseReport(
        schema_version=RELEASE_GATE_SCHEMA_VERSION,
        status=status,
        cwd=str(workspace),
        checks=tuple(checks),
    )


def format_release_report(report: ReleaseReport) -> str:
    """生成适合本地发布前人工检查的紧凑文本报告。"""

    lines = [f"Release gate: {report.status}", f"Workspace: {report.cwd}"]
    lines.extend(f"- {check.name}: {check.status} - {check.summary}" for check in report.checks)
    return "\n".join(lines)


def run(argv: list[str] | None = None, *, stdout: TextIO | None = None) -> int:
    """解析发布门禁参数，以退出码向本地脚本或 CI 表达结果。"""

    parser = argparse.ArgumentParser(prog="minicode-lite-release")
    parser.add_argument("--cwd", default=".", help="Repository root to verify.")
    parser.add_argument("--json", action="store_true", help="Render the release report as JSON.")
    args = parser.parse_args(argv)
    report = run_release_gate(args.cwd)
    output = sys.stdout if stdout is None else stdout
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True), file=output)
    else:
        print(format_release_report(report), file=output)
    return 0 if report.status == "pass" else 1


def main(argv: list[str] | None = None) -> int:
    """提供 console script 和 ``python -m`` 共用的最薄入口。"""

    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "RELEASE_GATE_SCHEMA_VERSION",
    "ReleaseCheck",
    "ReleaseReport",
    "format_release_report",
    "run_release_gate",
]
