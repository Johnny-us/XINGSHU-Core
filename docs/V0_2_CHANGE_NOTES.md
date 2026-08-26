---
type: public-change-notes
system: xingshu-2.0
scope: public-core
status: candidate
version: 0.2
updated: 2026-08-26
governance_effect: none
activation_state: not_active
visibility: public
---

# XINGSHU-Core v0.2 Candidate Change Notes（候选变更说明）

## Candidate Additions（候选新增）

- State Separation Architecture 与 Draft 2020-12 Schema；
- Evidence Lifecycle Metadata Policy 与 Schema；
- Evidence-Proportional Adoption Policy Candidate 及保守分类测试；
- Pre-Execution Assessment Contract 与 Action / Assessment / Execution / Verification Schema；
- `CORE_MANIFEST.yaml`、Schema / Test Registry、Synthetic Fixtures、v0.1 ↔ v0.2 兼容测试和迁移文档。

## State（状态）

```yaml
release_stage: candidate
enabled_by_default: false
governance_effect: none
activation_state: not_active
authorization_effect: none
```

本候选并未实现、批准或宣布 Merge、Release、Adoption 或 Activation。Assessment 结果不产生 Authorization；Evidence-Proportional Adoption 仍只是 Policy Candidate，不是 Active Governance。

## Compatibility and Recovery（兼容与恢复）

v0.2 保持 Additive Optional（可选增量）。v0.1 Consumer 忽略新文件；v0.2 Consumer 在 Manifest 缺失时回到 v0.1；所有能力关闭时无新行为。恢复锚点是不可移动的 `v0.1.0-candidate` 历史身份。详见 [Migration Guide（迁移说明）](V0_1_TO_V0_2_MIGRATION.md)。

## Explicitly Not Included（明确不包含）

- Checkpoint Lifecycle；
- Context Routing；
- Model Capability Routing；
- CI Workflow；
- Personal Data、User Memory、真实 Evidence Payload、账号、设备、凭据或私人项目数据。

所有测试数据均为为本候选新生成的 Synthetic Data（合成数据），由项目 Apache-2.0 许可边界覆盖，未复制第三方或私人内容。
