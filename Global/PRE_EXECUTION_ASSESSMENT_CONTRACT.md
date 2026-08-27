---
type: public-core-runtime-contract
system: xingshu-2.0
scope: public-core
status: candidate
version: 0.2
updated: 2026-08-26
governed_by: Global/00_GLOBAL_GOVERNANCE.md
governance_effect: none
activation_state: not_active
authorization_effect: none
visibility: public
---

# Pre-Execution Assessment Contract（执行前评估契约）

## 1. Purpose and Runtime Boundary（目的与运行时边界）

本 Public Core v0.2 Candidate（公共核心 v0.2 候选）将 Action Request（动作请求）、Assessment Result（评估结果）、Execution Result（执行结果）与 Verification Result（验证结果）分为四个可追溯阶段。契约只验证边界和记录真实结果；实际外部动作由独立 Runtime（运行时）在当前有效授权内执行。

## 2. Non-Authorization Invariant（不产生授权不变式）

Assessment（评估）可以核对外部授权的存在、范围与时效，但不能创建、复制、延长、转移或扩大授权。

```text
assessment_outcome: ready_for_execution
!=
authorization
```

`ready_for_execution` 只表示评估时已存在的所有适用条件已通过，且必须同时显示 `authorization_effect: none`。

## 3. Action Request（动作请求）

Action 明确目标、动作类型、Scope（作用域）、预期影响、受影响方、风险、隐私、可逆性、授权要求与引用、Evidence Plan（证据计划）、Acceptance Criteria（验收条件）、Stop Conditions（停止条件）和 `idempotency_key`。真实执行参数留在受保护 Runtime，公共记录只保留 `parameters_schema_ref`。

## 4. Assessment Gate（评估门禁）

`ready_for_execution` 必须同时满足：

1. 目标身份与当前 Observed State（观测状态）匹配；
2. Governance、Risk、Privacy、Reversibility 和 Evidence Plan 全部通过；
3. `stop_condition_state: clear`；
4. 需要授权时，外部授权必须 `valid`、Scope 匹配且未过期；
5. 没有关键 `unknown`。

其他结果只能是 `needs_authorization`、`needs_more_evidence`、`blocked` 或 `deny`。

## 5. Execution Gate and Idempotency（执行门禁与幂等）

执行前必须重新核对 Assessment 未过期、目标未漂移、授权仍有效且 Stop Condition 未触发。任一不成立时不得开始，只能记录 `not_started|stopped`。

State Separation v0.2.1 的 `execute` Transition 使用 `assessment_ref` 关联本契约中的 `assessment_result`，再通过 `assessment_result.action_ref` 关联 `action_request`。Transition 不复制 `authorization_requirement`，也不因 `authorization_refs` 字段存在而把所有 Execute 视为需要授权。

- `authorization_evaluation.status: not_required` 允许 Transition 使用空 `authorization_refs`，但不替代 Risk、Privacy、Reversibility、Evidence Plan、Stop Conditions 与 `assessment_outcome` 的检查；
- `authorization_evaluation.status: valid` 只有在引用存在、Scope 匹配且 Freshness 为 `current` 时才能支持需要授权的执行；
- `required|missing|stale|out_of_scope|unknown` 均不能支持完整执行；
- Assessment 缺失、无法解析、过期，或 Action / Target 不匹配时 Fail Closed（默认拒绝）。

相同 `idempotency_key` 与语义相同 Action 重试返回 `duplicate_suppressed`；同一 Key 对应不同目标、Scope、参数摘要或授权引用时返回 `idempotency_conflict` 并拒绝执行。

## 6. Verification Gate（验证门禁）

Command Exit Code（命令退出码）为成功或 `executed_pending_verification` 不等于 `verified`。所有必要 Acceptance Criteria 必须 `pass`，Evidence Scope 必须匹配，且不存在未处理失败或不确定结果，才能记录 `verified`。稳定性分为 `single_observation`、`repeated`、`stably_verified` 或 `unknown`。

Runtime State / Runtime Readback Verification（运行状态 / 回读验证）与本节的 Outcome Verification（结果验证）相互独立。Runtime State 的 `validation_state: verified|stably_verified` 只验证该 Runtime State 或 Readback Basis，不得自动创建 `verification_outcome: verified`，也不得推导业务目标、Acceptance Criteria、项目完成或 Governance Activation。业务结果验证的正式机器记录仍是本契约的 `verification_result`。

## 7. Error and Safe Next State（错误与安全下一状态）

错误记录包含 Phase、稳定 Error Code（错误码）、不泄露私密信息的消息、技术可重试性、不透明引用与 `safe_next_state`。未知 Error Code 按 `internal_error + blocked` 处理，不得猜测为成功或可授权重试。

完整字段与枚举见 [`pre-execution-assessment.schema.json`](../schemas/v0.2/pre-execution-assessment.schema.json)。
