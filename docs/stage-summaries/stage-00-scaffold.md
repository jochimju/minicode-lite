# 阶段 00：项目脚手架和 Git 基线学习总结

## 主题

本阶段的主题是：先把 `minicode-lite` 从一个普通文件夹，变成一个真正可运行、可测试、可提交、可复现的 Python 项目。

大白话讲，阶段 0 不是在做 agent 功能，而是在搭“施工现场”：

- conda 环境是施工现场的工具箱。
- Python 包结构是房子的地基。
- CLI 入口是大门。
- pytest 是验收员。
- Git 提交和标签是施工记录。

后面要学 MiniCode 的 agent loop、工具系统、session、memory，都要站在这个地基上。如果阶段 0 不稳，后面每一层都会晃。

## 问题是什么

### 为什么要有阶段 0

你现在的目标不是“直接写一个很厉害的 agent”，而是从 0 理解 MiniCode 的 harness 工程。harness 可以先理解成“把模型、工具、命令行、测试、会话这些东西串起来的运行框架”。

如果一个项目连下面这些事情都做不到：

- `import minicode_lite` 成功；
- `python -m minicode_lite` 能跑；
- `python -m pytest -q` 能验证；
- 当前版本能被 Git 记录；

那后面写 `types.py`、`mock_model.py`、`agent_loop.py` 时，你就不知道问题到底出在业务逻辑，还是项目本身没搭好。

所以阶段 0 要解决的是“项目本身能不能被稳定运行和验证”的问题。

### 本阶段具体要解决的问题

1. 空目录不是 Python 项目，Python 不知道要导入哪个包。
2. 没有命令行入口，无法像真实 MiniCode 一样从终端启动。
3. 没有测试基线，后续每次改代码都只能靠手动试。
4. 没有 conda 环境记录，换一台机器或重装环境后很难复现。
5. 没有 Git 基线，每个学习阶段的代码无法清晰回退和对比。

## 解决方案

### 最小解决方案

阶段 0 没有急着实现 agent，而是只实现了一个很小但完整的闭环：

```text
conda 环境 -> Python 包 -> CLI 入口 -> 输出固定文本 -> pytest 验证 -> Git 提交和标签
```

具体做法：

- 用 `environment.yml` 记录 conda 环境。
- 用 `pyproject.toml` 声明这是一个 Python 项目。
- 创建 `minicode_lite/` 包目录。
- 在 `minicode_lite/main.py` 里实现最小 CLI。
- 在 `minicode_lite/__main__.py` 里支持 `python -m minicode_lite`。
- 用 `tests/test_smoke.py` 验证最小行为。
- 用 `stage-00` 标签标记阶段完成版本。

### 为什么这个方案足够

因为阶段 0 的目标不是功能多，而是证明项目骨架可用。

现在只要看到：

```text
MiniCode Lite ready
```

就说明这些东西已经串通了：

- Python 能找到包；
- 包能找到入口；
- 入口能执行；
- 输出是稳定的；
- 测试能验证它。

这就是阶段 0 的最小闭环。

## 工作原理

### 你要建立的心智模型

把当前项目想象成一个未来会越来越复杂的命令行 agent。真实 MiniCode 启动时会做很多事情：加载配置、创建工具注册表、选择模型、加载记忆、进入 TUI、运行 agent loop。

但阶段 0 只保留最薄的一层：

```text
用户启动程序 -> main.run() -> 打印 ready -> 退出
```

它看起来简单，但这个入口后面会逐步接上：

- 阶段 1：模型输出类型；
- 阶段 2：工具注册表；
- 阶段 3：agent loop；
- 阶段 5：headless 单轮模式。

### 入口有两条路

第一条路：模块方式运行。

```powershell
python -m minicode_lite
```

这条路会进入：

```text
minicode_lite/__main__.py -> minicode_lite.main.main()
```

第二条路：安装后的命令行脚本。

```powershell
minicode-lite
```

这条路来自 `pyproject.toml`：

```toml
[project.scripts]
minicode-lite = "minicode_lite.main:main"
```

意思是：当用户运行 `minicode-lite` 命令时，Python 会调用 `minicode_lite.main` 模块里的 `main` 函数。

### 为什么要有 `run(argv, stdout)`

`main.py` 里没有把所有逻辑都写死在 `main()` 里，而是拆出一个 `run(argv, stdout)`。

这样做是为了测试方便：

- 测试可以传入假的参数 `argv`；
- 测试可以传入 `StringIO` 接收输出；
- 不需要真的打开一个终端进程；
- 行为更容易断言。

大白话讲：`main()` 是给真实用户用的，`run()` 是给测试和未来内部调用用的。

### 当前核心流程

```text
用户命令
  -> __main__.py 或 console script
  -> main()
  -> run()
  -> argparse 解析参数
  -> 打印 ready 或 version
  -> 返回退出码 0
```

## 对应核心文档

参考项目路径：

- `D:\JavaProject\MiniCode-Python-main`

本阶段对应的真实 MiniCode-Python 模块和理解重点：

- `pyproject.toml`
  - 学习真实项目如何声明包名、Python 版本、依赖、命令入口。
  - 真实项目里有 `minicode-py`、`minicode-headless`、`minicode-readiness` 等入口。
- `minicode/main.py`
  - 学习 CLI 入口负责“组装运行时”，而不是把所有业务逻辑都塞在一个函数里。
  - 阶段 0 只保留最小入口，后续再逐步接入工具、模型、权限、session。
- `Docs/Documentation/STRUCTURE.md`
  - 学习入口模块在整个 harness 中的位置。
  - 重点看“入口与运行时”部分。

## 学习产出

### 新增代码

- `minicode_lite/__init__.py`
  - 定义包版本 `__version__`。
- `minicode_lite/__main__.py`
  - 支持 `python -m minicode_lite`。
- `minicode_lite/main.py`
  - 实现阶段 0 的 CLI 入口。

### 新增测试

- `tests/test_smoke.py`
  - 验证包能导入。
  - 验证默认 CLI 输出 `MiniCode Lite ready`。
  - 验证 `--version` 输出 `0.0.1`。

### 新增文档和配置

- `README.md`
  - 说明项目目标、conda 环境、阶段 0 smoke。
- `environment.yml`
  - 记录 conda 环境依赖。
- `pyproject.toml`
  - 定义项目元数据、测试配置、命令入口。
- `.gitignore`
  - 忽略缓存、构建物、环境文件和临时目录。
- `docs/stage-summaries/stage-00-scaffold.md`
  - 当前这份复习文档。

### 本阶段最终能力

完成后，这个项目已经能做到：

- 可以在 conda 环境中运行；
- 可以作为 Python 包导入；
- 可以通过命令行启动；
- 可以通过 pytest 验证；
- 可以用 Git 的 `stage-00` 标签回到阶段 0。

## 测试验证

执行过的验证命令：

```powershell
conda run -n minicode-lite python -m pytest -q
conda run -n minicode-lite python -m minicode_lite
conda run -n minicode-lite minicode-lite
conda run -n minicode-lite minicode-lite --version
```

验证结果：

- `python -m pytest -q`：`3 passed`。
- `python -m minicode_lite`：输出 `MiniCode Lite ready`。
- `minicode-lite`：输出 `MiniCode Lite ready`。
- `minicode-lite --version`：输出 `0.0.1`。

这些测试验证的是“项目入口可用”，不是 agent 能力。agent 能力从阶段 1 开始逐步出现。

## 和真实 MiniCode-Python 的差异

### 保留的设计

- 使用 `pyproject.toml` 管理包和命令入口。
- 使用 pytest 做自动化验证。
- CLI 入口保持薄，方便后续把复杂逻辑拆进独立模块。
- 从一开始就要求每阶段有 Git 提交和标签。

### 简化的设计

真实 `minicode/main.py` 会做很多运行时初始化：

- 读取配置；
- 创建模型适配器；
- 创建工具注册表；
- 初始化权限管理；
- 加载 memory；
- 启动 TUI 或处理 headless；
- 保存 session。

阶段 0 全部不做，只保留一个 ready 输出。这样是故意的，因为我们先要确认“项目能跑”，再确认“agent 能跑”。

### 后续再实现的设计

- 阶段 1：核心类型和脚本化模型。
- 阶段 2：工具注册表。
- 阶段 3：最小 agent loop。
- 阶段 5：headless 单轮模式。
- 阶段 7：session 持久化。

## 常见误区

- 误区 1：觉得输出一句 ready 没意义。
  - 其实它证明了包结构、命令入口、安装配置、测试环境都通了。
- 误区 2：一开始就想接真实大模型。
  - 真实模型不稳定、依赖 key、网络和 provider。学习 harness 时，先用 mock 更稳。
- 误区 3：只手动运行，不写测试。
  - 后续阶段会不断改入口和模块，没有测试很容易把阶段 0 的基础弄坏。

## 复习提示

下次复习时，重点理解：

- `pyproject.toml` 为什么是 Python 项目的“身份证”。
- `python -m minicode_lite` 为什么会找 `__main__.py`。
- `minicode-lite` 命令为什么能映射到 `minicode_lite.main:main`。
- 为什么 CLI 逻辑要拆成可测试的 `run(argv, stdout)`。

可以尝试自己回答：

- 如果删除 `__main__.py`，`python -m minicode_lite` 会发生什么？
- 如果删除 `[project.scripts]`，`minicode-lite` 命令会发生什么？
- 如果没有 pytest，后面怎么证明阶段 1 没弄坏阶段 0？

## 面试高频问题与参考答案

### 1. 一个最小但合格的 Python 项目脚手架通常包含哪些部分？

**参考答案：** 至少应包含包目录、`pyproject.toml`、可执行入口、测试目录和版本控制基线。包目录承载运行时代码，`pyproject.toml` 描述构建后端、项目元数据、依赖和 console script，测试目录验证安装与入口契约，Git 提交和标签则让每个学习阶段可以准确回溯。脚手架的价值不是“目录看起来完整”，而是让安装、导入、执行、测试和交付形成最小闭环。

### 2. `pyproject.toml` 中的构建系统配置和 `[project.scripts]` 分别解决什么问题？

**参考答案：** 构建系统配置告诉 Python 工具使用什么后端把源码构建成可安装项目，例如 setuptools；`[project.scripts]` 则把一个命令名映射到 Python 函数，例如 `minicode-lite = "minicode_lite.main:main"`。前者解决“如何构建和安装”，后者解决“安装后用户如何启动”。console script 最终仍是薄包装，业务逻辑应放在可直接调用和测试的函数中。

### 3. 为什么 CLI 的 `main()` 应尽量薄，而不是把业务逻辑全部写进去？

**参考答案：** 薄入口可以把参数解析、业务执行和进程退出分开。这样测试能够直接调用 `run()` 或其他核心函数，不需要反复启动子进程，也更容易注入输出流、工作目录和测试替身。真正的 `main()` 只负责连接操作系统入口与可测试函数，可以降低 CLI 与 harness 核心逻辑的耦合。

### 4. 为什么阶段 0 只做 smoke test，也仍然有工程价值？

**参考答案：** smoke test 验证的是最基础但会阻断一切后续工作的契约：包能否导入、入口能否调用、最小输出是否稳定。它不能证明功能正确，但能快速发现包发现规则、模块路径、console script 映射或环境安装错误。阶段 0 的目标是验证工程骨架，而不是提前测试尚未存在的 agent 行为。

### 5. Git 提交和阶段标签有什么区别？为什么两个都需要？

**参考答案：** 提交记录一次代码状态及其父历史，分支会继续移动；标签是指向特定提交的稳定名字。`stage-01` 之类的标签让我们能准确创建该阶段完成时的 worktree，而不会随着 `main` 前进。提交回答“发生了什么变化”，标签回答“哪个提交代表这个里程碑”。

### 6. 为什么 `.env`、API key 和临时输出不能进入版本库？

**参考答案：** Git 历史具有传播性和持久性，敏感值即使后来删除，也可能仍存在于旧提交、远端副本和其他开发者克隆中。临时输出与本机环境数据还会造成不可复现的噪声。因此应在 `.gitignore` 中排除它们，只提交不含真实凭据的示例配置，并在提交前检查 `git status` 和暂存内容。

### 7. 场景题：本地可以 `python minicode_lite/main.py`，但安装后执行 `minicode-lite` 报入口不存在，你会如何排查？

**参考答案：** 先检查 `pyproject.toml` 的 `[project.scripts]` 名称和 `模块:函数` 是否正确，再确认目标函数真实存在且返回契约合理；随后重新安装项目，排除旧环境仍使用历史元数据；最后检查当前 shell 调用的是哪个 Python 环境以及命令解析到哪个可执行文件。直接运行源码成功，只能证明文件可执行，不能证明打包元数据和安装入口正确。

### 8. 为什么阶段 0 不直接复制真实 MiniCode 的完整目录和依赖？

**参考答案：** 学习 harness 的关键是逐步建立因果关系。如果一开始复制完整项目，入口、模型、工具、权限和会话层会同时出现，很难判断某个对象为何存在，也难写小而稳定的测试。阶段 0 只建立可安装、可测试、可提交的骨架，把复杂度推迟到出现明确问题的阶段，这是一种可验证的增量设计。

## 下一阶段衔接

阶段 0 搭好了外壳，阶段 1 要开始定义 agent harness 的“语言”。

也就是说，阶段 1 不会马上运行工具，而是先回答一个更基础的问题：

```text
模型到底应该用什么数据结构告诉 harness：
我是要直接回复，还是要调用工具？
```

阶段 0 的产物会这样支撑阶段 1：

- `minicode_lite/` 包目录已经存在，可以新增 `types.py` 和 `mock_model.py`。
- pytest 已经配置，可以新增 `test_types.py` 和 `test_mock_model.py`。
- conda 环境已经可用，可以继续用同一套命令验证。
