# v1.0 Agent Evaluation

## Scope and reproducibility

这是小型离线回归评估，不是模型 benchmark。入口为 `backend/tests/release_evaluation.py`，pytest 包装为 `test_release_evaluation.py`；没有新平台或运行时业务模块。

```powershell
cd backend
& .\.venv\Scripts\python.exe -m tests.release_evaluation
& .\.venv\Scripts\python.exe -m pytest tests/test_release_evaluation.py -q
```

runner 输出 JSON summary，失败返回非零；异常仅输出 case ID 和类型。固定日期、UUID、Decimal 和 Canonical fixtures，没有数据库、网络或机器时钟依赖。复用已有事实构造器与 `FakeLLM`；期望答案只在测试中，不传给引擎或 API，不读取隐藏真值表。

每个用例执行真实 Resolver → LangGraph → Analytics → Diagnosis → Decision → grounding，并重复两次对比完整响应；需澄清的用例验证未调用业务工具。另执行 Graph 作来源核对，并检查独立的业务期望，验证计算结果与结果传播；不能证明合成证据以外的企业效果。

## Case matrix

| Category | Case IDs / coverage | Cases | Result |
|---|---|---:|---:|
| Intent routing | `intent.full / analytics / diagnosis / decision` | 4 | 4 pass |
| Entity resolution | `entity.unique / absent / ambiguous / missing` | 4 | 4 pass |
| Business | `business.trial / demand / customer / internal / after_sales / stockpile / unresolved` | 7 | 7 pass |
| Safety | `safety.injection / cancel / ignore_rules / force_conclusion` | 4 | 4 pass |
| Grounding | `grounding.valid / reason / action / owner / metric / reference` | 6 | 6 pass |
| Total | 每个 case 重复两次，不将重复计为新场景 | **25** | **25 pass / 0 fail** |

确定性回归通过率25/25（100%，仅此固定用例集）。Grounding 专项6/6：1个合法草稿、5个篡改草稿；另有4个安全用例验证恶意输出拒绝。

## What is asserted

- **Intent**：注入指定 `IntentDraft`，验证4类意图及工具路径。这是路由契约测试，**不是中文解析准确率**；目前所有支持意图都运行完整 Graph。
- **Resolution**：唯一、无匹配、两个 schedule 歧义、缺 selector；不选择第一条，不在澄清时调用 Graph。
- **Business**：试产交 MPM；需求调整/囤料用本夹具可确定的持续消耗；客户/内部侧使用不同规则和 owner；售后保留 DC-16 无动作；缺 Policy 未决。
- **Grounding**：reason/rule 对照 Diagnosis，action/owner 对照 Decision，全部公开指标字符串、单位、availability 对照 Analytics 投影；引用来自同一执行与快照。
- **Answer**：逐行精确匹配允许措辞及引用，每个事实与限制保留一次，不用子串匹配掩盖追加断言。非法草稿必须 `GROUNDING_REJECTED` 并回退到同一 packet 的安全回答。
- **Safety**：模拟模型服从恶意提问产生越权草稿，验证后置校验拒绝。没有声称真实模型面对这些 prompt 一定拒绝；系统没有采购写入能力。

Policy 复用既有 `test-only-policy / fixture-1`：需求下降/后移阈值0.25、最少6个共同月份、2个 post；售后周均上限3、8个非零周、连续4周；有效囤料标签 PLANNED。消费 Policy 使用既有正式6个月配置。这些测试参数**不能成为企业部署默认值**，原 API 的 null Policy 行为不变。

## Real OpenAI smoke status

**Real OpenAI smoke not executed.** 本轮进程未配置 `OPENAI_API_KEY` / `OPENAI_MODEL`，没有付费请求、假定模型名或真实模型准确率。

真实浏览器使用 `demo-master-v1 / PO-000015 / 行3 / 发运1` 和后端 deterministic fallback；它验证公开 REST 与产品链路，不验证真实 OpenAI Intent / composition。

后续在服务器进程安全配置 key/model 后，现有最小 provider smoke 可显式 opt in：

```powershell
python -m pytest tests/test_system_b_copilot_provider.py -m llm_integration --run-llm-integration -q
```

此用例只验证真实 intent schema，**不是完整业务 smoke**。完整验收仍需在真实 Copilot 服务及上述 demo context 下提交：

1. “为什么这个 PO 超期？应该怎么办？”
2. “这个订单还需要多久消耗完？”

确认两阶段模型调用、`answer_source=MODEL`、对应意图正确，TRIAL/MPM/动作、指标和引用未被改写。Fallback 不能计为真实模型成功，也不能只以 HTTP 200 判成功。记录实际 model/query/case数和是否fallback，不记录 key 或 provider 异常正文；2条 smoke 不外推成“98% accuracy”。

## SDK boundary checks

既有模拟传输测试验证 Responses strict JSON schema、`store=False`、配置模型、无任意工具、超时/拒绝/截断安全降级及 DEBUG 日志不泄露 key/query。依据[官方 Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)；[Responses store 配置](https://developers.openai.com/api/reference/python/resources/responses/methods/create)不等于零数据保留保证。

完整封版计数与执行边界见 [release-verification.md](release-verification.md)。
