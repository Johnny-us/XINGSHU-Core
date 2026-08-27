---
type: public-change-notes
system: xingshu-2.0
scope: public-core
status: candidate
version: 0.2.1-candidate
updated: 2026-08-27
governance_effect: none
activation_state: not_active
visibility: public
---

# XINGSHU-Core State Separation v0.2.1 Candidate Change Notes（候选修订变更说明）

## Status（状态）

本变更是 Package A 范围内的 State Separation v0.2.1 Candidate Implementation（状态分离候选实现）。它仅提供待独立复核的规范、Schema、合成测试与兼容性证据，不构成 Merge（合并）、Release（发布）、Adoption（采用）、Activation（激活）或新的 Governance / Execution Authorization（治理 / 执行授权）。该能力继续默认关闭。

## G1 — Conditional Authorization Association（条件授权关联）

v0.2.1 为 `execute` 类型的 `state_transition` 增加必需的 `assessment_ref`，并采用以下唯一关联链：

`state_transition.assessment_ref → assessment_result.action_ref → action_request.authorization_requirement`

- `authorization_requirement.required: false` 且 Assessment 明确为 `not_required` 时，Transition 的 `authorization_refs: []` 合法；
- `authorization_requirement.required: true` 时，Assessment 必须返回 `valid`，授权引用必须存在、与 Transition 一致、Scope 匹配且仍为 `current`；
- `required|missing|stale|out_of_scope|unknown`、Assessment 缺失 / 无法解析 / 过期、Action 或 Target 不匹配均 Fail Closed（默认拒绝）；
- Risk、Privacy、Reversibility、Evidence Plan、Stop Conditions、Assessment Outcome 与规范可识别的必要条件仍分别检查；`not_required` 不绕过其他门禁；
- Transition 不复制 `authorization_requirement`，也不新增 `action_ref`，从而避免第二判断来源。

## G2 — Runtime Verification Boundary（运行验证边界）

Runtime State 的 `validation_state: verified|stably_verified` 可用于表示 Runtime State 或 Runtime Readback（运行回读）本身已验证。它不会自动创建 `verification_outcome`，也不证明业务 Acceptance Criteria、项目完成、Adoption 或 Governance Activation。业务结果验证仍由 Pre-Execution Assessment Contract 中独立的 `verification_result` 表达。

## Schema and Test Additions（结构与测试新增）

- 新增 `schemas/v0.2.1/state-separation.schema.json`，使用独立 `$id` 与 `schema_version: "0.2.1"`；
- 新增 v0.2.1 State Separation Conformance（符合性）测试与 3 个合成 Fixture；
- 新增 v0.2 ↔ v0.2.1 Compatibility（兼容性）测试；
- 测试覆盖条件授权、未知值保守拒绝、运行验证边界以及旧 / 新 Schema 不互相解释。

## Compatibility and Recovery（兼容与恢复）

- 原 `schemas/v0.2/state-separation.schema.json`、v0.2 Records 与 v0.2 Fixtures 保持原身份，不要求 `assessment_ref`；
- v0.2.1 Execute Record 只能按 v0.2.1 Schema 解释，不得反向迁移或降级成 v0.2 Record；
- 撤回或不选择 v0.2.1 Candidate Revision 时，Consumer 仍可继续处理 v0.2 Records；对 v0.2.1 Records 应返回 `unsupported_version`、忽略未请求且未启用的候选能力，或 Fail Closed；
- “撤回 v0.2.1 候选修订”和“禁用整个 State Separation Capability 并恢复 v0.1 解释路径”是两个独立状态，均不得改写历史记录。

## Preserved Boundaries（保持不变的边界）

- `manifest_version` 保持 `0.2`；
- Evidence Lifecycle、Pre-Execution Assessment 与 v0.3 Knowledge / Memory 能力版本不变；
- Public Core / Personal Instance 隔离不变；
- 不包含 Runtime Engine、CLI、真实执行、真实凭据、私人路径或 Personal Data；
- PR #3 的分支、提交与历史不在本 Package 范围内；
- Merge、Tag、Release、Adoption、Activation 与 Governance 修改均未授权、未执行。
