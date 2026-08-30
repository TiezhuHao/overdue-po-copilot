# ADR 0001: System B layers and deterministic business decisions

Status: Accepted for Phase 0 / Phase 1A.

## Context

本项目需要可运行、可测试、可解释的采购分析。System A 已提供普通业务证据及独立隐藏真值；公开 REST 与底层 schema 的覆盖度并不相同。直接让 LLM 读取宽报表并承担核心判断，会混淆数据缺失、规则计算和语言解释，难以复现或评测。

## Decision

System B 仅经 REST 访问 System A。Adapter 处理 HTTP、类型校验和无业务推断的映射；Canonical Models 隔离源展示结构。未来 Analytics 执行显式数值计算，Diagnosis 执行固定业务顺序和五类原因，Decision 执行已确认的责任与处置规则。未来 LLM/Agent 只能编排工具、解释证据和返回结果，不能代替这些规则，也不能访问隐藏真值。

本阶段选择同一 Python 工程内独立 `app/system_b` 命名空间，复用已锁定 Settings/httpx/Pydantic/pytest，不新增部署服务、SDK 或数据库。DTO 在 Adapter 私有边界，canonical 不导入 System A DTO、ORM 或 query service。缺失稳定 ID、历史查询、金额来源明确记录，不“合理默认”。

## Consequences

优点：无需运行服务即可测试 Adapter；未来规则可以独立确定性评测；接口变化集中在 DTO/映射；证据、计算与自然语言解释可分别审计。

代价：需要显式维护消费端字段映射；目前 API 缺口使稳定 Join、历史囤料和部分 Analytics 暂不能完整实施。允许本阶段交付传输与类型基础，不虚称诊断已经可用。未知上游展示列不透传，新增消费字段需契约和测试同步更新。

本 ADR 不批准新业务阈值或售后规则，也不启动 Analytics、Diagnosis、Decision、Agent、LLM、RAG 或前端开发。
