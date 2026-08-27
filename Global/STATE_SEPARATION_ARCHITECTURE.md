---
type: public-core-architecture
system: xingshu-2.0
scope: public-core
status: candidate
version: 0.2.1
updated: 2026-08-27
governed_by: Global/00_GLOBAL_GOVERNANCE.md
governance_effect: none
activation_state: not_active
visibility: public
---

# State Separation Architecture（状态分离架构）

## 1. Purpose and Candidate Boundary（目的与候选边界）

本候选架构区分“被声明的状态”、“实际运行状态”、“有证据支持的观测状态”和“基于规则的决定状态”，避免计划、命令成功、验证与授权被混写。它是 Public Core v0.2.1 Candidate（公共核心 v0.2.1 候选），默认关闭，不修改 Active Governance（当前有效治理）。v0.2.1 是对 State Separation Capability（状态分离能力）的候选修订；原 v0.2 Schema 与记录身份保持不变。

## 2. Four State Kinds（四类状态）

| `state_kind` | Meaning | Required Basis | Must Not Claim |
|---|---|---|---|
| `source` | 计划、声明或输入中的状态 | `source_ref`, `declared_at`, `declaration_type` | 已运行、已验证或已决定 |
| `runtime` | 运行对象的实际回读 | `runtime_ref`, `sampled_at`, `runtime_readback` | 仅凭 Runtime 状态声称业务结果已验证 |
| `observed` | 由当前、范围匹配 Evidence（证据）支持的观测 | `observed_at`, `evidence_refs`, `claim_refs`, `freshness` | 超出 Evidence Scope（证据作用域）的结论 |
| `decision` | 基于规则、证据与授权状态的分类结果 | `decision_outcome`, `governance_basis_refs`, `authorization_status` | 自行创建或扩大授权 |

`decision_effect` 固定为 `classification_only`。`decision_outcome: allow` 仍不等于执行授权。

Runtime State（运行状态）的 `validation_state: verified|stably_verified` 可以表示当前 Runtime State 或 Runtime Readback Basis（运行回读依据）本身已经得到验证。它不得自动推导 Business Outcome（业务结果）、Acceptance Criteria（验收条件）、项目完成或 Governance Activation（治理激活）。业务结果验证必须由 [Pre-Execution Assessment Contract（执行前评估契约）](PRE_EXECUTION_ASSESSMENT_CONTRACT.md) 中独立的 `verification_result.verification_outcome` 表达。

## 3. Transition Contract（转换契约）

State Transition（状态转换）必须显式记录原状态、目标状态、条件结果、Evidence 引用、Authorization 引用、时间与结果。

- `source → runtime`：`execute` 必须通过 `assessment_ref` 关联当前有效的 Assessment（评估）。Transition 不复制 `authorization_requirement`；它通过 `assessment_ref → assessment_result.action_ref → action_request.authorization_requirement` 使用 Pre-Execution Assessment 的唯一正式判断。
- Assessment 明确认定授权 `not_required` 时，`authorization_refs: []` 是合法状态，但 Risk、Privacy、Reversibility、Evidence Plan、Stop Conditions 和 Assessment Outcome 仍必须分别通过。
- Assessment 明确认定需要授权时，授权必须 `valid`、Scope 匹配、当前有效，并能追溯到本次 Action / Assessment。Assessment 缺失、无法解析、过期、不允许执行、授权缺失 / 过期 / 越界 / 未知，或 Action / Assessment / Transition 不匹配时 Fail Closed（默认拒绝）。
- `runtime → observed`：需要真实回读与当前、范围匹配的 Evidence。
- `observed → decision`：需要适用的 Governance Basis（治理依据），并保留 Evidence 时效与范围。
- 缺失必要条件、未知枚举、过期 Evidence、Scope Drift（作用域漂移）或缺少授权时 Fail Closed（默认拒绝）。

`condition_results` 当前没有机器字段区分“必要条件”和“附加信息”。v0.2.1 只对正式规范能够识别的必要条件执行 Fail-Closed；不得把任意无关 Condition（条件）自动升级为授权或新的必要条件。无法可靠判断条件角色时返回 `unknown|needs_review`，不得猜测为通过。

## 4. Record Contract（记录契约）

顶层 v0.2.1 记录使用 Schema Version `0.2.1`、Opaque Record ID（不透明记录标识）、RFC 3339 时间和受限 `extensions`。核心对象禁止额外字段；未知扩展可被忽略，但不得覆盖核心枚举、放宽安全默认、产生授权或改变治理效力。

v0.2.1 完整字段、枚举与约束的唯一机器入口为 [`state-separation.schema.json`](../schemas/v0.2.1/state-separation.schema.json)。原 [`v0.2 Schema`](../schemas/v0.2/state-separation.schema.json) 继续只解释 `schema_version: "0.2"` 记录。

## 5. Compatibility and Recovery（兼容与恢复）

v0.1 Consumer（消费者）可忽略未启用的 v0.2 / v0.2.1 文件。未支持 Schema Version 或必需枚举时返回 `unsupported_version` 或 `unknown_enum`，并停止对应能力。

v0.2 与 v0.2.1 是不可互相伪装的记录身份：v0.2 Record 不需要 `assessment_ref`，v0.2.1 Execute Transition 必须包含 `assessment_ref`；不得用 v0.2 Schema 重新解释 v0.2.1 Record，也不得通过反向迁移将 v0.2.1 降级为 v0.2。撤回或不选择 v0.2.1 Candidate Revision（候选修订）时，Consumer 仍可使用原 v0.2 路径处理 v0.2 Records。禁用整个 State Separation Capability 并恢复 v0.1 解释路径是另一项独立回退状态。两种回退均不重写历史记录或移动旧 Tag。
