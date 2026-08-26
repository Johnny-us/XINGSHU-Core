# Schema Registry（结构定义注册表）

本文件是 XINGSHU-Core 公共 Schema 的唯一导航入口。当前所有 v0.2 Schema 均为 Candidate（候选）、默认关闭，使用 JSON Schema Draft 2020-12。

| Schema | ID | Capability | Status |
|---|---|---|---|
| [State Separation](v0.2/state-separation.schema.json) | `urn:xingshu:core:schema:v0.2:state-separation` | `state_separation` | `candidate / disabled` |
| [Evidence Lifecycle](v0.2/evidence-lifecycle.schema.json) | `urn:xingshu:core:schema:v0.2:evidence-lifecycle` | `evidence_lifecycle` | `candidate / disabled` |
| [Pre-Execution Assessment](v0.2/pre-execution-assessment.schema.json) | `urn:xingshu:core:schema:v0.2:pre-execution-assessment` | `pre_execution_assessment` | `candidate / disabled` |

Evidence-Proportional Adoption（证据比例采用）只定义分类 API 语义，不新建第四个 Schema。未知必需枚举或不支持版本必须 Fail Closed（默认拒绝）。
