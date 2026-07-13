from __future__ import annotations

# 支持 `python -m minicode_lite` 的模块入口，不在这里重复 CLI 逻辑。

from minicode_lite.main import main


if __name__ == "__main__":
    # 将 CLI 返回的整数状态码交给解释器，供终端和脚本判断运行结果。
    raise SystemExit(main())
