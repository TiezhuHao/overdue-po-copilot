# v1.0 Interview Guide

## 30秒介绍

我做了一个超期采购订单诊断与决策支持系统。它不只计算订单有多老，还结合历史预测、项目生命周期、囤料和未来需求，通过确定性规则输出原因与只读处理建议，再由受证据约束的中文 Copilot 解释。前端可以从列表进入详情、追问并展开规则证据。公开演示全部使用可重复的合成企业数据，缺证据时明确保持未决。

## 为什么做 System A？

真实企业 ERP、计划与 BI 无法作为公开求职数据。六张表独立随机造数容易产生跨表矛盾，所以先建立统一企业世界，再派生 PostgreSQL、六类报表和 REST。System B 以 Adapter 集成，模拟真实系统边界；隐藏真值与业务 API 隔离。

## 为什么不用 LLM 直接判断？

采购规则需要 deterministic、testable、traceable、auditable。年龄公式、版本窗口、分支顺序和动作映射应能被固定输入复现。LLM 只提取受控意图和编排允许措辞；数值、原因、动作、owner 或引用不一致就拒绝草稿并 fallback。

这个取舍牺牲自由文风，换取可核对的事实边界。不能将受控措辞系统描述成已验证的任意自然语言推理系统。

## LangGraph 做什么？

维护单次状态、编排 Context → Analytics → Diagnosis → Decision 四个工具并记录 trace。规则在独立引擎，不让模型自由调用数据库或执行采购操作。当前4种受支持意图都运行完整依赖链，尚未优化为部分工具路径。

## 最大技术难点

- **跨报表身份**：PO Header/Line/Schedule、material/project/dataset 不能用名称代替稳定键，同一物料跨订单也不能串证据。
- **版本语义**：dataset、Forecast、weekly snapshot、Stockpile 各有身份与时间；历史囤料按下单日，不使用未来版本或数组顺序猜版本。
- **未知与不匹配**：`NOT_EVALUABLE` 不是 `NOT_MATCHED`，不能用于排除高优先级规则并自动落入内部呆滞。
- **Diagnosis / Decision 分离**：原因成立不代表动作规格完整。售后可已诊断，但 DC-16 阻止正式动作。
- **Grounded answer**：schema 合法不等于事实正确，仍需核对数值、角色、动作、引用和不可遗漏的限制。

## 如果接真实企业系统怎么办？

替换或扩展 Adapter，将真实 API 映射到已确认 Canonical Contract，尽量保持 Domain 和引擎不变。但不承诺“换 URL 即可”：还需确认单位、价格、供应承诺、历史生命周期、版本窗口、缺失语义及权限。企业阈值经业务确认，不使用测试 Policy。

## 两分钟演示

`demo-master-v1` → `PO-000015 / 行3 / 发运1` → 179天越界 → TRIAL → MPM确认处理 → 问“为什么这个 PO 超期？应该怎么办？” → 展开 Evidence。

订单来自公开 REST，原因与动作来自确定性引擎，回答引用规则/版本。再看未决订单，展示系统不会在缺 Policy 或零预测时补造答案。准确区分“参考项目 / 最大贡献项目”与责任归属。

## 如何描述测试与模型状态？

“有完整后端回归、前端构建和测试，以及25个重复执行的离线发布评估。模型输出在离线评估中是模拟的，验证路由和 grounding 边界，不是模型准确率。本次封版未配置 OpenAI key/model，真实产品演示走 deterministic fallback；真实模型完整 smoke 尚未执行。”

最终计数见 [封版验证记录](release-verification.md)，不引用旧阶段数量。没有线上用户、真实性能或节省金额数据，不编造收益。

## 当前限制

缺 PO price/currency；ASN/PR 与 confirmed/planned supply 组成未确认；公开历史 lifecycle 查询不足；DC-16、零需求动作、持续消耗 owner 等缺口保留。无认证、采购写回、持久聊天或生产部署；公开 Copilot 投影不含所有引擎指标。真实模型尚待独立验收。本轮不继续开发这些能力。
