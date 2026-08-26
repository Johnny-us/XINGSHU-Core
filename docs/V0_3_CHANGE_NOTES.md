---
type: public-release-notes
system: xingshu-2.0
scope: public-core
status: candidate
version: 0.3-candidate
updated: 2026-08-26
governance_effect: none
activation_state: not_active
visibility: public
---

# XINGSHU-Core v0.3 Change Notes（变更说明）

## Status（状态）

v0.3 当前为 Candidate（候选）。本变更集只提供公共模型、Schema、模板、测试与案例，不构成 Adoption（采用）、Activation（激活）、Release（发布）或 Implementation Authorization（实施授权）。所有新增能力默认关闭。

## Added（新增）

- 扩展 `Global/KNOWLEDGE_LIFECYCLE.md`，加入 Memory Distillation（记忆提炼）、来源核实、去重 / 冲突、晋升审查和事件触发复审；
- 新增 `Global/KNOWLEDGE_OBJECT_MODEL.md`，定义 `main / appendix / provenance`、`source / derived_view` 与三个独立状态维度；
- 新增 `Global/MIGRATION_PROVENANCE.md`，定义来源清单、映射、遗漏、源保护、冲突与迁移状态；
- 新增 3 个 v0.3 JSON Schema 和 3 个可复制模板；
- 新增 10 类强制失败 / 保守降级场景及正向合成夹具；
- 新增匿名 NaiveBridge 知识迁移案例。

## Preserved（保持不变）

- Evidence Lifecycle 的状态仍为独立枚举，未被知识状态复制或替换；
- v0.2 State Separation、Evidence Lifecycle、Evidence-Proportional Adoption 与 Pre-Execution Assessment 文件和 Schema 保持原有语义；
- `CORE_MANIFEST.yaml` 的格式版本保持 `0.2`，v0.3 能力作为 Additive Optional（增量可选）且默认关闭，使既有 Consumer 可以按未知禁用能力规则忽略；
- v0.1 恢复基线、Core / Personal Instance 边界与公开隐私边界保持不变。

## Fail-Closed Boundaries（失败关闭边界）

- 缺少来源的记忆候选不得晋升；
- 陈旧证据不能支撑“当前已验证”结论；
- `reasoned_inference` 未经必要审查不得成为 `active`；
- `historical`、`superseded` 与 `deprecated` 对象不得作为当前结论加载；
- Appendix 不得成为第二正式来源，Derived View 不得反写 Source；
- 跨平台本地路径复用在 Scope 不匹配时拒绝；
- 任一迁移来源必须有映射或带原因的遗漏记录；
- `migration_state: migrated` 不会将 `runtime_validation_state` 自动变为 `verified`。

## Compatibility and Rollback（兼容与回退）

v0.3 不要求单独的 v0.2 → v0.3 数据迁移：未请求 v0.3 能力的 Consumer 可以继续按 v0.2 语义运行。回退时禁用并忽略 v0.3 Memory Entry、Knowledge Object 与 Migration Provenance 记录；不得改写 v0.2 历史或把 v0.3 状态压回 Evidence State。

## Not Included（不包含）

- 自动将聊天或历史资料晋升为正式记忆；
- Personal Instance 的私人 Memory Store、Embedding（向量表示）或检索实现；
- 自动修改源库、自动删除迁移来源或自动解决冲突；
- Runtime Engine（运行时引擎）、数据库、索引器或 UI；
- Merge、Tag、Release、Adoption、Activation 或 Active Governance 修改。
