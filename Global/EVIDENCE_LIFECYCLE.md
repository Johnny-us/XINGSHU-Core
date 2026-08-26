---
type: public-core-policy
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

# Evidence Lifecycle（证据生命周期）

## 1. Purpose and Boundary（目的与边界）

本 v0.2 Candidate（候选）定义可公开、可迁移的 Evidence Metadata（证据元数据）契约。它记录 Evidence 能支持什么结论、适用于什么对象、环境、版本和时间，以及何时必须复核。它不收集或公开原始 Payload（载荷），不产生 Authorization（授权）或 Governance Effect（治理效力）。

## 2. Required Metadata（必需元数据）

每项 `evidence_metadata` 包含稳定记录标识、被验证对象引用、`validation_scope`、`provenance`、`observed_at`、`validation_method`、`evidence_state`、`freshness`、`privacy_classification`、`payload_handling`、`review_triggers`、`relationships` 与 `claim_refs`。

`validation_scope` 必须同时限定：

- Subject Identity（主体身份）的不透明引用；
- 可支持的 Claim（结论）；
- State Domain（状态域）与 Environment Class（环境类别）；
- Version Constraint（版本约束）与 Time Window（时间窗口）；
- 已知 Scope Limitation（作用域限制）。

Evidence 不得支持超出上述任一维度的结论。

## 3. Lifecycle States（生命周期状态）

| State | Meaning | Current Claim Support |
|---|---|---|
| `current` | 当前方法、范围和时效均有效 | 仅在 Scope 内支持 |
| `stale` | 已过期或触发复核但未重新验证 | 不支持当前完成声明 |
| `superseded` | 已被新 Evidence 取代 | 仅供追溯 |
| `corrected` | 已由新记录纠正 | 仅供纠错链追溯 |
| `historical` | 只描述过去的观测 | 不证明当前状态 |
| `invalid` | 来源、完整性或方法不可靠 | 不可使用 |
| `unknown` | 无法确认当前状态 | Fail Closed（默认拒绝） |

`validation_method.result: not_run` 不得与能支持当前结论的 `current` 状态并存。

## 4. Freshness, Review and Correction（时效、复核与纠错）

达到 `valid_until` 或命中时间、对象、版本、环境、治理、冲突证据、方法失效或 Scope 变化触发器后，`current` 必须重新评估；在复核完成前至少转为 `stale`。

纠错使用 Append-First（追加优先）：保留原记录，新建纠正记录，并通过 `corrects` / `corrected_by` 双向关系建立可追溯链。不得通过删除旧 Evidence 伪造“从未出错”。

## 5. Public / Private Separation（公共与私人分离）

Public Metadata 禁止包含 Payload、内容正文、Secret（秘密值）、Credential（凭据）、Token、Cookie、本地路径、邮箱、账号、设备、个人身份或聊天原文，也不得通过 `extensions` 绕过。`payload_handling` 只能说明 `not_collected`、`external_private`、`redacted` 或 `synthetic_public`。

完整机器契约见 [`evidence-lifecycle.schema.json`](../schemas/v0.2/evidence-lifecycle.schema.json)。
