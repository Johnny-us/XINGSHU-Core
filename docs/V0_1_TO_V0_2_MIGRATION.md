---
type: public-migration-guide
system: xingshu-2.0
scope: public-core
status: candidate
version: 0.2
updated: 2026-08-26
governance_effect: none
activation_state: not_active
visibility: public
---

# v0.1 → v0.2 Migration（迁移）

## 1. Migration Character（迁移性质）

v0.2 是在 v0.1 文档 / 治理 Candidate（候选）上增加可选公共规范、Schema、Manifest 和测试的 Additive Public Structure Migration（增量公共结构迁移）。它不是 Personal Data Conversion（私人数据转换），不重写 v0.1 历史记录。

## 2. Compatibility Paths（兼容路径）

- v0.1 Consumer 读取 v0.2 Repository：忽略新增可选文件，继续 v0.1 语义。
- v0.2 Consumer 读取 v0.1 Repository：Manifest 缺失时安全回到 v0.1，不猜测 v0.2 存在或 Active。
- v0.2 Repository 但 Capability Disabled：不产生新状态、执行、同步或采用。
- 未知但未启用的可选能力可忽略；请求使用未知能力或不支持 Manifest Version 必须 Fail Closed（默认拒绝）。
- Public v0.2 到 Personal Instance：零自动同步，需要独立 Review、Opt-In（选择启用）、授权与验证。

## 3. Candidate Evaluation Sequence（候选评估顺序）

1. 核对恢复基线 `v0.1.0-candidate`。
2. 读取 [`CORE_MANIFEST.yaml`](../CORE_MANIFEST.yaml)，确认所有能力 `candidate / enabled_by_default: false`。
3. 仅在独立 Opt-In 与 Runtime 配置存在时评估对应 Schema；否则继续 v0.1 语义。
4. 执行 Conformance、Compatibility、Privacy、Personal Isolation 和 Rollback Validation。
5. 任一关键失败时停用 v0.2 发现路径，恢复 v0.1 解释，保留失败与纠错证据。

## 4. Rollback（回退）

回退不移动旧 Tag、不 force-push、不删除失败历史。候选未进入 `main` 时保留失败分支并停止扩散；若未来已进入公共历史，应通过新的纠正 Commit 恢复安全语义。Personal Instance 保持独立，不由公共回退自动改变。
