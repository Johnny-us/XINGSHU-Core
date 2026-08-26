---
type: public-core-architecture
system: xingshu-2.0
scope: public-core
status: candidate
version: 0.2
updated: 2026-08-26
governed_by: Global/00_GLOBAL_GOVERNANCE.md
governance_effect: none
activation_state: not_active
visibility: public
---

# State Separation Architecture（状态分离架构）

## 1. Purpose and Candidate Boundary（目的与候选边界）

本候选架构区分“被声明的状态”、“实际运行状态”、“有证据支持的观测状态”和“基于规则的决定状态”，避免计划、命令成功、验证与授权被混写。它是 Public Core v0.2 Candidate（公共核心 v0.2 候选），默认关闭，不修改 Active Governance（当前有效治理）。

## 2. Four State Kinds（四类状态）

| `state_kind` | Meaning | Required Basis | Must Not Claim |
|---|---|---|---|
| `source` | 计划、声明或输入中的状态 | `source_ref`, `declared_at`, `declaration_type` | 已运行、已验证或已决定 |
| `runtime` | 运行对象的实际回读 | `runtime_ref`, `sampled_at`, `runtime_readback` | 业务结果已验证 |
| `observed` | 由当前、范围匹配 Evidence（证据）支持的观测 | `observed_at`, `evidence_refs`, `claim_refs`, `freshness` | 超出 Evidence Scope（证据作用域）的结论 |
| `decision` | 基于规则、证据与授权状态的分类结果 | `decision_outcome`, `governance_basis_refs`, `authorization_status` | 自行创建或扩大授权 |

`decision_effect` 固定为 `classification_only`。`decision_outcome: allow` 仍不等于执行授权。

## 3. Transition Contract（转换契约）

State Transition（状态转换）必须显式记录原状态、目标状态、条件结果、Evidence 引用、Authorization 引用、时间与结果。

- `source → runtime`：需要当前 Assessment（评估）；需授权的动作还必须有有效且范围匹配的授权引用。
- `runtime → observed`：需要真实回读与当前、范围匹配的 Evidence。
- `observed → decision`：需要适用的 Governance Basis（治理依据），并保留 Evidence 时效与范围。
- 缺失必要条件、未知枚举、过期 Evidence、Scope Drift（作用域漂移）或缺少授权时 Fail Closed（默认拒绝）。

## 4. Record Contract（记录契约）

顶层记录使用 Schema Version `0.2`、Opaque Record ID（不透明记录标识）、RFC 3339 时间和受限 `extensions`。核心对象禁止额外字段；未知扩展可被忽略，但不得覆盖核心枚举、放宽安全默认、产生授权或改变治理效力。

完整字段、枚举与约束的唯一机器入口为 [`state-separation.schema.json`](../schemas/v0.2/state-separation.schema.json)。

## 5. Compatibility and Recovery（兼容与恢复）

v0.1 Consumer（消费者）可忽略未启用的 v0.2 文件。未支持 Schema Version 或必需枚举时返回 `unsupported_version` 或 `unknown_enum`，并停止对应能力。回退通过禁用该候选能力并恢复 v0.1 解释路径完成，不重写历史记录或移动旧 Tag。
