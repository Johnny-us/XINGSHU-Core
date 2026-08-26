---
schema_version: "0.3"
record_type: migration_provenance
migration_id: migration-example
target_topic_ref: topic-example
migration_state: in_progress
runtime_validation_state: not_run
source_unchanged: true
source_change_basis_refs: []
governance_effect: none
activation_state: not_active
---

# Migration Provenance（迁移溯源）

> 本模板记录“来源去了哪里、为什么这样处理”。它不证明运行已经验证，也不授予删除源材料、执行、公开、采用或发布权限。

## 迁移目标

- 目标主对象：
- 目标附录：
- 目标溯源对象：
- 迁移范围：

## 来源清单

| Source ID | 来源类别 | 匿名来源引用 | 时间戳 | 完整性校验 |
|---|---|---|---|---|
| source-001 | historical_record | source:example-001 |  |  |

## 映射与取舍

| Source ID | 目标对象 / 章节 | 处理方式 | 原因 |
|---|---|---|---|
| source-001 | knowledge-example / 核心知识 | merged | 示例说明 |

## 未迁移项

| Source ID | 原因代码 | 原因 | 由何处覆盖 |
|---|---|---|---|
| 无 |  |  |  |

任何来源若既没有映射，也没有带原因的未迁移记录，迁移不得标记为 `migrated`。

## 冲突

- 未解决冲突：无 / 填写双方来源、受影响结论和 `needs_review` 路由

## 源材料保护

- 是否保持源材料不变：`true`
- 只读 / 前后校验证据：
- 若源材料发生合法变化，外部依据引用：无 / 填写匿名 Authorization、审计或正当依据引用
- 是否获得删除源材料授权：否

`source_change_basis_refs` 只记录外部依据引用，不保存授权正文，也不由本记录产生 Authorization；`authorization_effect` 保持 `none`。

## 独立状态

- Migration State（迁移状态）：`in_progress`
- Runtime Validation State（运行验证状态）：`not_run`

`migrated` 不等于 `verified`。迁移完成但尚未现场验证时，应明确写作 `migrated / pending_verification`。

## 隐私与边界

只记录匿名元数据和引用；不复制原始私人载荷、身份、账号、设备、Secret、私人路径或聊天正文。
