---
type: public-core-adoption-policy-candidate
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

# Evidence-Proportional Adoption Policy Candidate（证据比例采用策略候选）

## 1. Purpose and Non-Effect Boundary（目的与无效力边界）

本 Public Core v0.2 Candidate（公共核心 v0.2 候选）根据能力来源、Evidence（证据）质量、Context Delta（环境差异）、风险、隐私和不可免除门禁，为候选能力建议 Review Route（审查路径）。它不是 Active Governance（当前有效治理），不产生 Authorization（授权）、Adoption（采用）或 Activation（激活）。

所有 Classification Result（分类结果）必须固定返回：

```yaml
authorization_effect: none
governance_effect: none
activation_effect: none
```

## 2. Classification Inputs（分类输入）

`classify_adoption` 接受 `api_version`、不透明请求与能力引用、`intended_scope`、`origin_type`、Evidence Summary（证据摘要）、`context_delta`、`risk_level`、`affected_party_impact`、`privacy_boundary_state`、`authorization_state` 与六项 `non_waivable_gate_states`。

未知、缺失、矛盾或不支持值不得近似映射为通过；只能返回稳定 Error Code（错误码）或更保守的 `needs_review`。

## 3. Candidate Classes（候选分类）

| Class | Appropriate Starting Point | Required Direction |
|---|---|---|
| `class_1` | Design Hypothesis（设计假设）、Single Case（单案例）、过期或薄弱证据 | 继续 Discovery、Case Validation 和 Generalization Review |
| `class_2` | 经多案例验证的模式，且证据质量、相关性、时效、独立性和覆盖无关键缺口 | 继续 Schema/API、Compatibility、Privacy、Risk 与 Owner Review |
| `class_3` | 无公共晋升目标的 Personal Instance / Project Private Extension | 留在私人边界，不降低其风险、隐私或授权门禁 |
| `needs_review` | 作用域、隐私、风险、来源或输入相互冲突 / 未知 | 不得自动采用或进入执行 |

Class 是 Evidence Maturity Route（证据成熟度路由），不是 Risk Level（风险等级）。高风险只能增加或保留控制，不得因证据更多而删除 Owner、Privacy、Authorization、Compatibility、Verification 或 Rollback Gate。

## 4. Conservative Rules（保守规则）

- `personal_instance` / `project_private` 且无公共晋升目标时建议 `class_3`。
- 只有 `validated_case_pattern` 且 Evidence 五维无 `weak|unknown`、Context Delta 已复核时才能建议 `class_2`。
- `design_hypothesis`、`single_case`、证据过期或未解决的差异进入 `class_1|needs_review`。
- `mixed`、作用域不清、Privacy `violated|unknown`、关键风险未知或输入冲突必须 `needs_review`。
- 分类不得将 `unsatisfied|unknown` 门禁改为 `satisfied`，也不得复制或延长外部授权。

## 5. Output Contract（输出契约）

结果必须包含 `recommended_class`、非数值的 `confidence`、`reason_codes`、`required_review_route`、`non_waivable_gates`、`missing_evidence`、`reclassification_triggers` 及三项固定 `none` Effect。当 Evidence 过期、环境改变、风险上升或新冲突证据出现时，必须重新分类。
