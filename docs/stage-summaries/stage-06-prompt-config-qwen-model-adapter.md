# 阶段 06：prompt、配置和 Qwen 模型适配器学习总结

## 主题

本阶段的主题是：把只会使用 mock model 的最小 harness，升级为可配置的运行时；配置完整时连接 DashScope Qwen/OpenAI-compatible 接口，配置缺失时仍安全地使用 mock。

大白话讲，前五个阶段已经有了能稳定演练的“训练模式”。阶段 6 增加一扇受控的“真实模型门”：门的钥匙是模型名、接口地址和 API key，三者齐全才开门；少任何一个就留在训练模式，不让整个程序因配置不全而停摆。

## 问题是什么

### 为什么要有这个阶段

真实 agent harness 不能把模型名、服务地址和凭据散落在 CLI、agent loop 或工具里。那会让测试难以隔离，也会让配置优先级和凭据泄露变得不可控。另一方面，学习项目不能因为没有账号、网络或额度就无法运行，所以必须保留可预测的 mock 后备路径。

### 本阶段具体要解决的问题

1. 从环境变量、`.env` 和可选 JSON settings 读取运行时配置，并明确优先级。
2. 构造包含工作目录、工具和运行时边界信息的 system prompt。
3. 在 registry 边界决定使用真实 Qwen adapter 还是 mock adapter。
4. 将本地消息和工具协议映射为 OpenAI-compatible Chat Completions 请求，再还原为 `AgentStep`。
5. 验证真实 endpoint 的连接，但让该验证默认不消耗 API 配额。

## 解决方案

### 最小解决方案

- `RuntimeConfig` 和 `load_runtime_config()` 统一读取配置，采用“环境变量 > `.env` > settings JSON”的逐字段优先级。
- `build_system_prompt()` 把 cwd、已注册工具、权限和 memory 占位信息组合成模型可见的运行时说明。
- `create_model_adapter()` 只在配置完整时创建 `QwenModelAdapter`，否则回退到 `MockModelAdapter`。
- `QwenModelAdapter` 负责消息、工具和响应的协议转换；连续本地工具调用会恢复成同一批 provider `tool_calls`。
- `tests/test_live_qwen.py` 使用 `live_qwen` marker。只有 `MINICODE_LITE_LIVE_QWEN_TEST=1` 且配置完整时才会联网；否则跳过。

### 为什么这个方案足够

这里的目标是先跑通一次非流式 Chat Completions 调用，而不是提前复制完整 provider 层。streaming、多 provider 路由、复杂重试和自动 fallback 链会在后续有明确需求时再加入。当前 mock 路径使离线开发和绝大多数测试保持稳定。

## 工作原理

### 你要建立的心智模型

配置层像一个隔离舱：它读取敏感输入，却只向外提供“是否完整”和不含密钥的诊断。模型注册表像一个岔路口：完整配置走真实 adapter，不完整配置走 mock。agent loop 始终只面对 `ModelAdapter` 和 `AgentStep`，不必知道请求来自哪一家 provider。

### 核心对象解释

#### `RuntimeConfig` 和 `load_runtime_config`

`RuntimeConfig` 保存模型名、base URL、API key 和安全诊断。`is_qwen_configured` 只有在三项均非空时才为真。加载器逐字段执行优先级，因此某一来源只配置一部分字段时，其他字段仍可向低优先级来源补齐。

#### `build_system_prompt`

prompt 构建器把静态规则和动态运行时信息合并。它让模型知道当前工作目录与可用工具，但不承担执行工具或选择 provider 的职责。

#### `create_model_adapter`

registry 是真实模型与 mock 的唯一选择点。CLI 或 headless 不需要复制“是否配置完整”的分支，后续增加其他 adapter 也能保留同一个上层接口。

#### `QwenModelAdapter`

适配器把 `ChatMessage` 转为 provider messages，把 `ToolRegistry` 定义转为 function tools，并把成功响应归一化为 `AgentStep`。它拒绝 HTTP 重定向，避免 `Authorization` 被自动转发到未知目标；错误信息不带 API key。

### 当前核心流程

```text
环境变量 / .env / settings JSON
  -> load_runtime_config
  -> RuntimeConfig.is_qwen_configured
  -> create_model_adapter
  -> QwenModelAdapter 或 MockModelAdapter
  -> AgentStep
```

真实调用中的消息流：

```text
ChatMessage + ToolRegistry
  -> QwenModelAdapter 序列化
  -> /chat/completions
  -> provider message / tool_calls
  -> AgentStep
  -> agent loop
```

## 对应核心文档

参考项目路径：`D:\JavaProject\MiniCode-Python-main`

- `minicode/config.py`
  - 学习配置来源、优先级和不泄露敏感值的诊断边界。
- `minicode/prompt.py`
  - 学习 system prompt 如何组合静态规则与当前运行时上下文。
- `minicode/model_registry.py`
  - 学习 provider 选择与 fallback 应在 registry，而非 agent loop。
- `minicode/openai_adapter.py`
  - 学习本地消息、工具调用和 OpenAI-compatible 请求/响应的转换边界。

## 学习产出

### 新增和扩展的代码

- `minicode_lite/config.py`：运行时配置读取、优先级和安全诊断。
- `minicode_lite/prompt.py`：system prompt 构建。
- `minicode_lite/model_registry.py`：真实 Qwen 与 mock 的统一选择入口。
- `minicode_lite/qwen_adapter.py`：DashScope/OpenAI-compatible 非流式 adapter。
- `minicode_lite/headless.py`、`minicode_lite/main.py`：运行时配置接入和 CLI 凭据脱敏输出。

### 新增测试

- `tests/test_config.py`、`tests/test_prompt.py`、`tests/test_model_registry.py`、`tests/test_qwen_adapter.py`：使用临时配置或 fake transport 覆盖离线行为。
- `tests/test_live_qwen.py`：带 `live_qwen` marker 的 opt-in 真实连通性测试。

### 本阶段最终能力

- 没有完整真实配置时，项目继续走 mock fallback。
- 配置来源按明确优先级合并，诊断不回显凭据。
- Qwen 请求不会跟随重定向，降低认证头转发风险。
- CLI 输出会对凭据做脱敏处理。
- 连续工具调用在 provider 请求中保持为同一个工具调用批次。

## 测试验证

本阶段的验证命令是：

```powershell
python -m pytest -q
python -m pytest tests/test_live_qwen.py -m live_qwen -q
```

2026-07-13 的新鲜运行结果：

- `python -m pytest -q`：`71 passed, 1 skipped`。
- `MINICODE_LITE_LIVE_QWEN_TEST=1 python -m pytest tests/test_live_qwen.py -m live_qwen -q`：`1 passed`，真实 DashScope endpoint 成功返回 assistant 响应。

常规全量测试仍在 live 开关未启用时跳过网络调用，避免日常测试消耗 API 配额。本阶段收尾时通过临时环境变量显式启用测试，并在本地 `.env` 的完整配置下完成一次真实连通性验证；测试输出没有包含 API key。

离线测试重点验证：配置优先级、settings 解析、mock 回退、prompt 动态内容、请求/响应映射、工具批次保留、错误脱敏和拒绝重定向。

## 和真实 MiniCode-Python 的差异

### 保留的设计

- 把配置、prompt、provider adapter 和 registry 分开。
- 让 agent loop 只处理统一的 `AgentStep`，不耦合 provider 协议。
- 将敏感值限制在配置和传输边界，并提供 mock 后备。

### 简化的设计

- 只实现单一 Qwen/OpenAI-compatible 非流式路径。
- 没有完整的 provider 路由、streaming、重试策略或模型能力探测。
- prompt 只注入当前阶段的 cwd、工具、权限和 memory 占位信息。

### 后续再实现的设计

- 阶段 7 增加路径、编辑和命令执行的明确审批边界。
- 后续阶段再将 session、checkpoint、memory、readiness 和更丰富的 provider 行为接入 runtime。

## 常见误区

- 误区 1：有 API key 就应当总是使用真实模型。
  - 正确理解：模型名、base URL 和 key 必须同时完整；否则使用 mock，避免部分配置导致模糊网络错误。
- 误区 2：把密钥放进诊断或 CLI 输出可以方便排查。
  - 正确理解：诊断只能报告变量名和状态，CLI 必须脱敏，测试也不输出请求头或密钥。
- 误区 3：工具调用逐条存储，就应逐条发送给 provider。
  - 正确理解：本地历史便于逐条配对工具结果，provider 侧必须恢复连续调用批次，保持协议语义。
- 误区 4：HTTP 重定向只是普通网络细节。
  - 正确理解：带认证头的请求若自动跳转，可能把授权转交给非预期目标，所以 adapter 明确拒绝重定向。
- 误区 5：live test 应默认运行。
  - 正确理解：真实测试可能消耗配额，必须由显式环境开关启用，并在配置不完整时跳过。

## 复习提示

下次复习时，重点理解：

- 为什么配置优先级要逐字段处理，而不是整份文件二选一？
- 为什么 mock fallback 是学习 harness 的安全默认值？
- `RuntimeConfig`、model registry 和 adapter 的职责边界分别是什么？
- 为什么工具批次、认证头和 CLI 诊断都属于 provider 安全边界？

可以尝试自己回答：

- 环境变量只设置了 model，`.env` 设置了 base URL 和 key，最终配置来自哪里？
- agent loop 为什么不应该直接判断 API key 是否存在？
- 连续两个 `assistant_tool_call` 在 provider 请求里应当长什么样？
- 为什么 live test 要同时检查显式开关和配置完整性？

## 面试高频问题与参考答案

### 1. 为什么运行时配置要集中加载，而不能让各模块直接读取环境变量？

**参考答案：** 集中加载可以统一配置来源、优先级、默认值和诊断规则，并把敏感值限制在明确边界内。如果 adapter、CLI 和 registry 各自读取环境变量，同一个字段可能采用不同名字或优先级，测试也难隔离本机环境。`RuntimeConfig` 让上层依赖一个确定对象，而不是依赖散落的全局状态。

### 2. 为什么配置优先级要逐字段合并，而不是整份来源二选一？

**参考答案：** 用户可能只用环境变量覆盖 model，而 base URL 和 key 仍来自 `.env` 或 settings。如果高优先级来源只要存在一个字段就整份覆盖，其他字段会意外丢失。逐字段采用“环境变量 > `.env` > settings”既保留明确优先级，也支持部分覆盖；测试要覆盖混合来源而不只是完整配置。

### 3. 为什么配置不完整时回退 mock，而不是带着半份配置调用真实模型？

**参考答案：** 真实调用至少需要模型名、base URL 和 API key 形成完整条件，半份配置只会产生模糊网络或认证错误。mock fallback 保证学习项目离线可运行，单元测试也不依赖外部服务。与此同时应提供不含密钥的诊断，告诉用户缺少哪些配置，避免回退行为变成不可见故障。

### 4. model registry 和 provider adapter 的职责有什么区别？

**参考答案：** registry 决定根据配置创建哪个 adapter，并返回选择诊断；adapter 负责把统一消息和工具定义转换成某个 provider 协议，再把响应还原成 `AgentStep`。registry 处理“选谁”，adapter 处理“怎么说话”。agent loop 不应判断 API key，也不应理解 HTTP 请求字段。

### 5. OpenAI-compatible 工具调用协议转换最容易出错的地方是什么？

**参考答案：** 常见错误包括 arguments JSON 编解码、工具调用 ID 配对，以及把同一 assistant step 的多次 tool calls 拆成多个 provider assistant 消息。本地历史为了执行方便可以逐条存储，但 adapter 发回 provider 时必须恢复连续批次，并把每个 tool result 关联到原调用 ID，否则 provider 会拒绝协议或模型失去上下文。

### 6. system prompt 为什么属于运行时组合层，而不应该硬编码在 adapter 中？

**参考答案：** system prompt 需要组合 cwd、工具清单、权限和 memory 等动态 harness 信息，这些与具体 provider 无关。adapter 只负责协议映射；把 prompt 硬编码进去会让不同 provider 重复业务规则，也难在测试中验证当前工具和工作区是否正确注入。prompt 构建器应输出稳定、可诊断且不含凭据的文本。

### 7. 场景题：provider 返回 302 重定向，为什么 adapter 不应直接带着 Authorization 自动跟随？

**参考答案：** 重定向目标可能不是原受信任主机，自动转发认证头会把 API key 暴露给非预期服务。安全做法是拒绝带凭据请求的自动重定向，报告受控错误，让配置方显式修正 base URL。测试可启动本地重定向服务器并断言目标服务从未收到请求头，这比只检查异常文本更有说服力。

### 8. live model test 为什么必须显式 opt-in？

**参考答案：** live test 会依赖网络、真实凭据、服务可用性和额度，默认运行会让普通回归测试变慢且不稳定，还可能产生费用。单元测试应用 fake transport 验证请求和响应映射，live test 只验证真实 endpoint 连通性，并同时要求显式环境开关和完整配置。跳过 live test 不代表没有测试 adapter 逻辑。

## 下一阶段衔接

本阶段解决了：

```text
统一、可诊断且默认安全的模型运行时选择。
```

阶段 7 要解决：

```text
真实模型可以提出文件和命令操作后，哪些行为允许直接执行，哪些必须请求审批。
```

本阶段产物会这样支撑下一阶段：

- 真实模型和 mock 都已统一为 `ModelAdapter`，权限层可放在工具执行边界而不是 provider 内部。
- prompt 已有权限摘要位置，阶段 7 可以把实际策略注入其中。
- registry、配置诊断和 live test 让真实调用的启用条件保持可见、可控。
