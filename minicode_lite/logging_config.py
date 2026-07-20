from __future__ import annotations

"""提供默认静默、可由入口或测试配置的最小结构化运行日志。"""

import logging
from time import perf_counter


# 所有子日志都归入同一命名空间，外部只需配置 minicode_lite logger。
LOGGER_NAME = "minicode_lite"


def get_logger(component: str) -> logging.Logger:
    """取得组件 logger；模块导入本身不创建文件或控制台 handler。"""

    return logging.getLogger(f"{LOGGER_NAME}.{component}")


def monotonic_milliseconds(started_at: float) -> float:
    """用单调时钟计算耗时，避免系统时间校准造成负数。"""

    return round((perf_counter() - started_at) * 1000, 3)


def log_tool_execution(tool_name: str, *, success: bool, duration_ms: float) -> None:
    """记录工具边界，不记录可能含源码、命令或凭据的输入输出。"""

    get_logger("tools").info(
        "tool_execution name=%s success=%s duration_ms=%.3f",
        tool_name,
        success,
        duration_ms,
        extra={"tool_name": tool_name, "success": success, "duration_ms": duration_ms},
    )


def log_turn_stop(reason: str, *, steps: int) -> None:
    """记录 agent turn 的明确停止原因和已消耗模型步数。"""

    get_logger("agent_loop").info(
        "turn_stop reason=%s steps=%d",
        reason,
        steps,
        extra={"stop_reason": reason, "steps": steps},
    )


__all__ = ["get_logger", "log_tool_execution", "log_turn_stop", "monotonic_milliseconds"]
