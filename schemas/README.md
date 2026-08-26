# Schema Registry（结构定义注册表）

本文件是 XINGSHU-Core 公共 Schema 的唯一导航入口。当前所有 v0.2 与 v0.3 Schema 均为 Candidate（候选）、默认关闭，使用 JSON Schema Draft 2020-12。

| Schema | ID | Capability | Status |
|---|---|---|---|
| [State Separation](v0.2/state-separation.schema.json) | `urn:xingshu:core:schema:v0.2:state-separation` | `state_separation` | `candidate / disabled` |
| [Evidence Lifecycle](v0.2/evidence-lifecycle.schema.json) | `urn:xingshu:core:schema:v0.2:evidence-lifecycle` | `evidence_lifecycle` | `candidate / disabled` |
| [Pre-Execution Assessment](v0.2/pre-execution-assessment.schema.json) | `urn:xingshu:core:schema:v0.2:pre-execution-assessment` | `pre_execution_assessment` | `candidate / disabled` |
| [Memory Entry](v0.3/memory-entry.schema.json) | `urn:xingshu:core:schema:v0.3:memory-entry` | `knowledge_memory_lifecycle` | `candidate / disabled` |
| [Knowledge Object](v0.3/knowledge-object.schema.json) | `urn:xingshu:core:schema:v0.3:knowledge-object` | `knowledge_object_model` | `candidate / disabled` |
| [Migration Provenance](v0.3/migration-provenance.schema.json) | `urn:xingshu:core:schema:v0.3:migration-provenance` | `migration_provenance` | `candidate / disabled` |

Evidence-Proportional Adoption（证据比例采用）只定义分类 API 语义，不新建第四个 Schema。未知必需枚举或不支持版本必须 Fail Closed（默认拒绝）。

v0.3 没有建立独立 Acceptance / Review Schema（验收 / 复审结构定义）：相关字段已由 Memory Entry 与 Knowledge Object 表达，以避免重复状态机。Evidence State（证据状态）、Conclusion / Document State（结论 / 文档状态）、Migration State（迁移状态）与 Runtime Validation State（运行验证状态）保持独立。
