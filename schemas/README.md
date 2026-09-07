# Schema Registry（结构定义注册表）

本文件是 XINGSHU-Core 公共 Schema 的唯一导航入口。当前所有 v0.2、v0.2.1 与 v0.3 Schema 均为 Candidate（候选）、默认关闭，使用 JSON Schema Draft 2020-12。

| Schema | ID | Capability | Status |
|---|---|---|---|
| [State Separation](v0.2/state-separation.schema.json) | `urn:xingshu:core:schema:v0.2:state-separation` | `state_separation` | `candidate / disabled` |
| [State Separation v0.2.1](v0.2.1/state-separation.schema.json) | `urn:xingshu:core:schema:v0.2.1:state-separation` | `state_separation` | `candidate / disabled` |
| [Evidence Lifecycle](v0.2/evidence-lifecycle.schema.json) | `urn:xingshu:core:schema:v0.2:evidence-lifecycle` | `evidence_lifecycle` | `candidate / disabled` |
| [Pre-Execution Assessment](v0.2/pre-execution-assessment.schema.json) | `urn:xingshu:core:schema:v0.2:pre-execution-assessment` | `pre_execution_assessment` | `candidate / disabled` |
| [Memory Entry](v0.3/memory-entry.schema.json) | `urn:xingshu:core:schema:v0.3:memory-entry` | `knowledge_memory_lifecycle` | `candidate / disabled` |
| [Knowledge Object](v0.3/knowledge-object.schema.json) | `urn:xingshu:core:schema:v0.3:knowledge-object` | `knowledge_object_model` | `candidate / disabled` |
| [Migration Provenance](v0.3/migration-provenance.schema.json) | `urn:xingshu:core:schema:v0.3:migration-provenance` | `migration_provenance` | `candidate / disabled` |

Evidence-Proportional Adoption（证据比例采用）只定义分类 API 语义，不新建第四个 Schema。未知必需枚举或不支持版本必须 Fail Closed（默认拒绝）。

State Separation v0.2 与 v0.2.1 是独立 Schema Identity（结构身份）。v0.2.1 为 `execute` Transition 增加必需的 `assessment_ref`；不支持或未选择 v0.2.1 的 Consumer 必须返回 Unsupported（不支持）或 Fail Closed，不得把 v0.2.1 Record 降级后交给 v0.2 Schema 解释。

v0.3 没有建立独立 Acceptance / Review Schema（验收 / 复审结构定义）：相关字段已由 Memory Entry 与 Knowledge Object 表达，以避免重复状态机。Evidence State（证据状态）、Conclusion / Document State（结论 / 文档状态）、Migration State（迁移状态）与 Runtime Validation State（运行验证状态）保持独立。

## Context Bridge Candidate Contracts（上下文桥接候选合同）

`context-bridge-candidate` 是 Context Bridge 候选合同使用的 Schema identity，不代表新的 XINGSHU Release、Tag、Governance、Activation、Runtime 或 Production version。

| Schema | ID | Object role | Status |
|---|---|---|---|
| [Context Candidate](candidate/context-bridge/context-candidate.schema.json) | `urn:xingshu:core:schema:candidate:context-bridge:context-candidate` | Unauthorized discovery candidate（未授权发现候选） | `candidate / disabled` |
| [Context Registration Proposal](candidate/context-bridge/context-registration-proposal.schema.json) | `urn:xingshu:core:schema:candidate:context-bridge:context-registration-proposal` | Suggestion-only registration proposal（仅建议的登记提案） | `candidate / disabled` |
| [Context Validation Artifact](candidate/context-bridge/context-validation-artifact.schema.json) | `urn:xingshu:core:schema:candidate:context-bridge:context-validation-artifact` | Deterministic validation evidence（确定性验证证据） | `candidate / disabled` |
| [Human Authorization Evidence](candidate/context-bridge/human-authorization-evidence.schema.json) | `urn:xingshu:core:schema:candidate:context-bridge:human-authorization-evidence` | Explicit human final-authorization evidence（明确的人类最终授权证据） | `candidate / disabled` |
| [Registered Context Reference](candidate/context-bridge/registered-context-reference.schema.json) | `urn:xingshu:core:schema:candidate:context-bridge:registered-context-reference` | Immutable registered context binding and lifecycle（不可变已登记上下文绑定与生命周期） | `candidate / disabled` |
| [Context Reference Transition](candidate/context-bridge/context-reference-transition.schema.json) | `urn:xingshu:core:schema:candidate:context-bridge:context-reference-transition` | Legal lifecycle-transition evidence（合法生命周期转换证据） | `candidate / disabled` |
| [Source Adapter Contract](candidate/context-bridge/source-adapter-contract.schema.json) | `urn:xingshu:core:schema:candidate:context-bridge:source-adapter-contract` | Read-only Source Adapter envelope（只读来源适配器契约） | `candidate / disabled` |
| [Trusted Client Profile](candidate/context-bridge/trusted-client-profile.schema.json) | `urn:xingshu:core:schema:candidate:context-bridge:trusted-client-profile` | Public shape for owner-controlled client identity（Owner 控制客户端身份的公共结构） | `candidate / disabled` |
| [Runtime Binding](candidate/context-bridge/runtime-binding.schema.json) | `urn:xingshu:core:schema:candidate:context-bridge:runtime-binding` | Fixed trusted-client / Reference / scope binding（固定可信客户端 / Reference / scope 绑定） | `candidate / disabled` |
| [Resolve Context](candidate/context-bridge/resolve-context.schema.json) | `urn:xingshu:core:schema:candidate:context-bridge:resolve-context` | Bounded request / result / error contract（有界请求 / 结果 / 错误合同） | `candidate / disabled` |
| [Derived Provider Metadata](candidate/context-bridge/derived-provider-metadata.schema.json) | `urn:xingshu:core:schema:candidate:context-bridge:derived-provider-metadata` | Derived, rebuildable, non-authoritative metadata（派生、可重建、非权威元数据） | `candidate / disabled` |

本节登记的 Context Bridge contracts 均为 candidate、disabled by default，且 `governance_effect=none`、`authorization_effect=none`、`activation_effect=none`。Schema Registry（结构定义注册表）的文档登记本身不启用 capability，不建立 Python Registry dispatch、Validator support 或 CLI support，不证明 Human Authorization，不激活 Runtime Binding，也不意味着 Runtime integration 或 production readiness。
