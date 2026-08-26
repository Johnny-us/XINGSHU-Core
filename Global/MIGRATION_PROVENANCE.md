---
type: global-policy
system: xingshu-2.0
scope: public-core
status: candidate
version: 0.3-candidate
updated: 2026-08-26
governed_by: Global/00_GLOBAL_GOVERNANCE.md
governance_effect: none
activation_state: not_active
visibility: public
---

# Migration Provenance（迁移溯源）

> 本文件定义知识迁移的公共追溯要求。它是 Execution Evidence（执行证据）与可审查记录，不是授权、采用、激活或发布机制。

## 1. Purpose（目的）

知识迁移会发生复制、合并、拆分、去重、改写、删减和结构调整。Migration Provenance 用于回答：哪些来源参与了迁移、每项内容去了哪里、哪些内容没有迁移、为什么做出取舍、源材料是否保持不变，以及迁移后哪些运行行为仍待验证。

迁移溯源不要求把源内容复制到 Public Core。公共记录只保存最少必要 Metadata（元数据）与匿名引用，不保存原始 Payload（载荷）、私人路径、账号、设备、身份或 Secret（秘密值）。

## 2. Required Record（必要记录）

适用于多来源合并、重要主题迁移或可能丢失语义的迁移记录，至少包含：

1. **Source Inventory（来源清单）**：稳定的来源 ID、来源类别、可公开的相对标识、时间戳，以及可用时的完整性哈希；
2. **Source Identity（来源身份）**：说明来源是原始资料、正式知识、派生视图、历史记录或外部资料；
3. **Mapping（映射）**：每个来源或来源片段映射到目标 `main`、`appendix` 或 `provenance` 的哪个部分；
4. **Merge / Dedup Decisions（合并 / 去重决定）**：记录重复内容如何合并、采用哪个依据以及保留哪些差异；
5. **Omitted Items（未迁移项）**：每个被省略的来源或片段必须有原因，例如重复、失效、超出范围、隐私边界或无法核实；
6. **Source Change Control（源材料变更控制）**：明确源材料是否保持不变；若保持不变，引用只读流程或完整性证据；若合法迁移需要改变来源，引用外部授权、审计或其他正当依据，但不复制 Authorization Payload（授权载荷）；
7. **Independent States（独立状态）**：分别记录 `migration_state` 与 `runtime_validation_state`；
8. **Conflicts（冲突）**：记录尚未解决的版本、平台、范围或结论冲突，以及安全的下一状态；
9. **Relationships（关系）**：目标对象、来源对象、替代关系和相关 Evidence 的引用。

## 3. Migration State（迁移状态）

| 状态 | 含义 |
|---|---|
| `not_migrated` | 尚未开始迁移 |
| `in_progress` | 已开始但映射、取舍或验收未完成 |
| `migrated` | 预定来源已完成映射、取舍和迁移记录 |
| `needs_review` | 来源、映射、冲突或遗漏原因仍需复核 |
| `not_applicable` | 对象不是迁移产生 |
| `unknown` | 无法确认，必须失败关闭 |

## 4. Runtime Validation State（运行验证状态）

| 状态 | 含义 |
|---|---|
| `not_run` | 未安排或尚未执行运行验证 |
| `pending_verification` | 已识别验证要求，但尚未取得充分结果 |
| `verified` | 在声明的环境、版本、范围和时间内通过验证 |
| `failed` | 运行验证未通过 |
| `stale` | 既有运行证据已过期或环境已漂移 |
| `unknown` | 无法确认，必须失败关闭 |

`Migration Complete（迁移完成） != Runtime Verified（运行已验证）`。迁移可以合法处于：

```yaml
migration_state: migrated
runtime_validation_state: pending_verification
```

这一组合表示文档迁移与溯源已经完成，但当前运行环境尚未验证。不得将其缩写成“全部完成”。

## 5. Source Protection（源材料保护）

- 默认以复制、只读读取或内容寻址的方式迁移；
- 不在迁移过程中顺手修正源库；源材料中的错误应在目标取舍或冲突记录中说明；
- `source_unchanged: true` 必须有可复核依据，例如只读流程、前后哈希或受控快照；
- `source_unchanged: false` 且迁移标记为 `migrated` 时，必须通过 `source_change_basis_refs` 引用外部授权、审计记录或其他正当变更依据；引用只证明依据可追溯，不由 Migration Provenance 自行创造 Authorization（授权）；
- `source_change_basis_refs` 只保存匿名 Metadata 引用，不保存真实授权正文、凭据或其他私人 Payload；`authorization_effect` 始终为 `none`；
- 未取得删除授权时，不因目标迁移成功而删除、改名或覆盖来源；
- Derived View（派生视图）不能反向覆盖 Source（源对象）。

## 6. Scope and Source Priority（作用域与来源优先级）

迁移应区分：

- 当前机器或实例的 Observed State（观测状态）；
- 可跨环境复用的 Procedure（流程）；
- 对特定版本有效的权威说明；
- 只供追溯的历史材料。

来源优先级必须针对具体 Claim（主张）与 Scope 建立，不能用一个全局排序机械覆盖所有内容。当前运行状态可以证明当前环境，但不能自动成为跨平台流程；版本化包内说明可以约束该版本的命令，但不能扩大治理或授权边界。发现来源冲突时进入 `needs_review`，不得静默选择较新文件。

跨平台复用路径、命令、端口或环境状态前，必须重新确认 `environment_class`、平台、版本和作用域。Scope 不匹配时拒绝加载为当前指令。

## 7. Omission and Conflict Rules（遗漏与冲突规则）

- 任一来源从迁移清单消失而没有 Omission Record（遗漏记录），迁移不得标记为 `migrated`；
- 省略重复内容仍需说明它由哪个目标结论覆盖；
- 因隐私或安全省略的内容只记录类别与原因，不复制敏感内容；
- 未解决冲突必须保留双方来源引用、受影响对象、临时安全状态和复审触发条件；
- 历史结论不得因迁移到新结构而重新成为 `active`。

## 8. Authorization Boundary（授权边界）

Migration Provenance 只证明迁移过程可追溯。它不证明目标内容正确，不证明运行环境已验证，不授予执行、公开、合并、发布、采用或代表权限。Handoff（交接）与迁移关系也只传递请求和证据，不传递授权。

## 9. Current Status（当前状态）

本文件为 Public Core v0.3 `candidate`，`governance_effect: none`、`activation_state: not_active`。实现、测试、Commit、Push、Pull Request 或 Merge 都不会自动改变该状态。
