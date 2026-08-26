---
type: global-architecture
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

# Knowledge Object Model（知识对象模型）

> 本文件定义 Public Core 的知识对象角色、来源形态和相互关系。它是 v0.3 Candidate（候选），不会因存在、测试通过或被合并而自动激活。

## 1. Purpose（目的）

Knowledge Object（知识对象）把“一项完整知识”与“一个巨大文件”分开。完整性来自唯一正式入口、可追溯关系和可到达的必要附录，而不是把所有正文、原始记录和历史都塞进同一文档。

同一 Topic（主题）与 Scope（作用域）只能有一个当前正式 `main`。对象可以由多个文件组成，但不能形成多个可竞争的 Source of Truth（唯一正式来源）。

## 2. Document Roles（文档角色）

| 角色 | 职责 | 约束 |
|---|---|---|
| `main` | 主题的唯一正式入口，保存核心结论、适用范围、主流程、关键验证与所有必要附录链接 | 同一主题与作用域只能有一个当前正式 `main` |
| `appendix` | 保存大型清单、字段表、日志、规则集或原始测试摘要 | 必须链接回 `main`，不得声明自己是第二正式入口 |
| `provenance` | 保存来源、迁移映射、取舍、历史和替代关系 | 只提供追溯，不自动证明当前结论有效，也不授予权限 |

主笔记不得把全部关键规则外包给附录。离开搜索功能时，读者仍应能从 `main` 找到所有完成判断、执行与验证所需的必要对象。

## 3. Origin Forms（来源形态）

| 来源形态 | 含义 | 写回边界 |
|---|---|---|
| `source` | 由正式作者、系统或受控迁移维护的源对象 | 按适用治理维护 |
| `derived_view` | 从一个或多个 Source 生成的索引、摘要、投影或展示 | 必须可重新生成；不得覆盖、改写或成为源对象的隐式替代 |

Derived View（派生视图）可以丢弃后重新生成。任何需要人工维护且会反向改变源结论的对象，都不能仅以 `derived_view` 绕过正式来源和审查。

## 4. Independent State Dimensions（独立状态维度）

知识对象按需同时表达三个维度：

```yaml
document_state: active
migration_state: migrated
runtime_validation_state: pending_verification
```

- `document_state`：对象的文档成熟度与当前知识地位；使用 [Knowledge Lifecycle（知识生命周期）](KNOWLEDGE_LIFECYCLE.md) 的结论状态。
- `migration_state`：内容是否已经完成映射、迁移与追溯；由 [Migration Provenance（迁移溯源）](MIGRATION_PROVENANCE.md) 约束。
- `runtime_validation_state`：对象所描述的运行行为是否在目标环境中得到验证。

三个状态不得互相推导。`migrated` 不等于 `verified`，`active` 不等于当前环境已经运行验证，运行命令成功也不等于文档验收或迁移完成。

## 5. Required Relationships（必要关系）

- `main` 通过显式关系列出必要的 `appendix` 与 `provenance`；
- `appendix` 与 `provenance` 必须通过 `main_ref` 回链所属主题；
- `derived_view` 必须列出 `derived_from`，并声明不写回源对象；
- 被取代对象通过 `supersedes` / `superseded_by` 保留双向历史；
- 对象引用的 Evidence（证据）使用 `evidence_refs`，不内嵌原始 Payload（载荷）；
- 跨平台或跨环境复用必须保留原 Scope，并在新 Scope 重新核实，不能复用本地路径或实例状态作为通用指令。

## 6. Completeness and Acceptance（完整性与验收）

知识对象可以声明完整，前提是：

1. 唯一 `main` 能说明用途、适用范围、核心结论与当前限制；
2. 所有必要附录可从 `main` 直接到达并回链；
3. 来源与取舍可通过 `provenance` 追溯；
4. 已知冲突、外部依赖和替代关系没有被隐藏；
5. 文档、迁移和运行验证状态分别如实表达；
6. 不包含 Secret（秘密值）、原始私人载荷、实例身份或不必要的绝对路径。

`appendix` 成为第二 Source of Truth、`derived_view` 覆盖源对象、历史对象作为当前对象加载，或跨平台路径被直接复用，均应 Fail Closed（失败关闭）为拒绝或 `needs_review`。

## 7. Boundary（边界）

本模型不决定某项知识是否应被采用，不授予写入、执行、发布或代表权限，也不改变 Evidence Lifecycle 的状态定义。Personal Instance 可以保存自己的对象实例与私人载荷，但不得将其自动同步回 Public Core。

## 8. Current Status（当前状态）

本文件为 Public Core v0.3 `candidate`，`governance_effect: none`、`activation_state: not_active`。Implementation（实现）、测试、Commit、Push 或 Pull Request 均不等于 Adoption、Release 或 Activation。
