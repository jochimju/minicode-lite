# 阶段 00：项目脚手架和 Git 基线 学习总结

## 主题

本阶段学习的主线：

- 把空目录变成一个可以在 conda 环境中导入、运行、测试和继续提交的 Python 项目。

## 问题是什么

为什么需要完成这个阶段：

- 当前 `minicode-lite` 只有文档和无效的 `.git` 目录，还不是一个真正可运行的 Python 项目。
- MiniCode harness 后续要逐步加入类型、模型、工具、agent loop、session 等模块；如果没有稳定脚手架，后续每个阶段都缺少运行和验证入口。

本阶段要解决的具体问题：

- 如何建立 Python 包结构，让 `import minicode_lite` 成功。
- 如何建立最小 CLI，让命令行可以证明项目入口可用。
- 如何建立 pytest 测试基线，让后续阶段每次修改都有回归检查。
- 如何记录 conda 环境，保证项目运行环境可复现。

## 解决方案

本阶段采用的最小实现方案：

- 创建 `pyproject.toml`，定义包名、Python 版本、pytest 配置和 `minicode-lite` 命令入口。
- 创建 `minicode_lite/` 包，提供 `__version__`、`main.py` 和 `python -m minicode_lite` 入口。
- 创建 `tests/test_smoke.py`，验证包可导入、CLI ready 输出和版本输出。
- 创建 `environment.yml`，记录 conda 环境依赖。

保留的能力：

- 标准 Python 包结构。
- 命令行入口。
- pytest 自动化验证。
- conda 环境复现说明。

暂时简化或后置的能力：

- 暂不实现模型适配器。
- 暂不实现工具注册表。
- 暂不实现 agent loop。
- 暂不实现 session、memory、readiness、TUI。

## 工作原理

核心流程：

```text
用户运行命令 -> minicode_lite.__main__ 或 console script -> minicode_lite.main.run -> 输出 ready/version
```

关键对象：

- `minicode_lite.__version__`：当前包版本。
- `minicode_lite.main.READY_MESSAGE`：阶段 0 的稳定 smoke 输出。
- `minicode_lite.main.run`：可测试的 CLI 执行函数。
- `minicode_lite.main.main`：console script 和 `python -m` 使用的入口。

数据如何流动：

- 测试传入 argv 和 StringIO。
- `run` 使用 argparse 解析参数。
- 默认输出 `MiniCode Lite ready`。
- `--version` 输出包版本。
- 测试断言退出码和输出文本。

## 对应核心文档

参考项目路径：

- `D:\JavaProject\MiniCode-Python-main`

本阶段对照阅读的真实模块、测试或文档：

- `pyproject.toml`：对照 console scripts、pytest 配置、包发现方式。
- `minicode/main.py`：对照 CLI 入口职责，但本阶段只保留最小输出。
- `Docs/Documentation/STRUCTURE.md`：对照“入口与运行时”部分，确认入口模块在 harness 中的位置。

## 学习产出

新增或修改的代码：

- `minicode_lite/__init__.py`：定义包版本。
- `minicode_lite/__main__.py`：支持 `python -m minicode_lite`。
- `minicode_lite/main.py`：实现阶段 0 CLI。

新增或修改的测试：

- `tests/test_smoke.py`：验证导入、ready 输出和版本输出。

新增或修改的文档：

- `README.md`：说明项目目标、conda 环境和阶段 0 smoke。
- `environment.yml`：记录 conda 环境。
- `docs/stage-summaries/stage-00-scaffold.md`：阶段 0 复习总结。

本阶段最终具备的能力：

- 项目可以作为 Python 包导入。
- 项目可以从命令行运行。
- 项目可以在 conda 环境中跑 pytest。
- 后续阶段有了最小测试和文档基线。

## 测试验证

执行的验证命令：

```powershell
conda run -n minicode-lite python -m pytest -q
conda run -n minicode-lite python -m minicode_lite
```

验证结果：

- `conda run -n minicode-lite python -m pytest -q` 通过，结果为 `3 passed`。
- `conda run -n minicode-lite python -m minicode_lite` 输出 `MiniCode Lite ready`。
- `conda run -n minicode-lite minicode-lite` 输出 `MiniCode Lite ready`。
- `conda run -n minicode-lite minicode-lite --version` 输出 `0.0.1`。

重点验证行为：

- `import minicode_lite` 成功。
- 默认 CLI 输出 `MiniCode Lite ready`。
- `--version` 输出 `0.0.1`。

## 和真实 MiniCode-Python 的差异

保留的设计：

- 使用 `pyproject.toml` 管理包和命令入口。
- 使用 pytest 作为测试基线。
- 入口模块独立于后续 agent runtime。

简化的设计：

- 真实 `minicode/main.py` 会初始化配置、权限、工具、模型、memory、TUI；本阶段只做 CLI smoke。
- 真实项目有多个命令入口；本阶段只有 `minicode-lite`。

后续再实现的设计：

- `headless.py` 单轮模式。
- `tooling.py` 工具注册表。
- `agent_loop.py` 模型-工具循环。
- `session.py` 持久会话。

## 复习提示

下次复习时，重点重新理解：

- 为什么 CLI 入口要保持薄，而核心逻辑放进可测试的 `run` 函数。
- 为什么第一阶段先用 smoke 测试，而不是直接写 agent loop。
- `pyproject.toml` 中 console script 是如何映射到 Python 函数的。

可以尝试自己回答：

- `python -m minicode_lite` 和 `minicode-lite` 命令分别走哪个入口。
- 为什么 `run(argv, stdout)` 比直接在 `main()` 里写死 `sys.argv` 和 `print` 更容易测试。

## 下一阶段衔接

本阶段产物如何支撑下一阶段：

- `minicode_lite/` 包目录已经存在，阶段 1 可以直接加入 `types.py` 和 `mock_model.py`。
- pytest 配置已经存在，阶段 1 可以继续新增 `test_types.py` 和 `test_mock_model.py`。
- conda 环境已经创建，后续阶段可以统一使用 `conda run -n minicode-lite ...` 验证。

下一阶段开始前要确认：

- 阶段 0 smoke 测试通过。
- Git 仓库已初始化并完成阶段 0 本地提交。
