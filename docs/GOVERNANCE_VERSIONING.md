---
type: governance-versioning
system: xingshu-2.0
scope: public-core
status: candidate
version: 0.1
updated: 2026-08-25
governed_by: Global/00_GLOBAL_GOVERNANCE.md
visibility: public
---

# Governance Versioning（公共治理版本规则）

## 1. Purpose & Authority（目的与效力）

本文件定义 XINGSHU Public Core（星枢公共核心）治理文件从候选、审查、生效、升级、弃用到回滚的统一生命周期。

本文件继承 [Global Governance（全局治理总纲）](../Global/00_GLOBAL_GOVERNANCE.md)，不得改变或削弱其中的用户主权、授权、隐私、安全、风险控制与 Core / Personal / Backup（核心 / 私人实例 / 备份）边界。边界定义以 [Core / Personal Boundary（核心与私人实例边界）](../CORE_PERSONAL_BOUNDARY.md) 为准；敏感信息处理同时遵守 [Security Policy（安全政策）](../SECURITY.md)。

Governance Version（治理版本）、Lifecycle Status（生命周期状态）、Git Tag（Git 标签）和 Personal Instance Adoption（私人实例采用状态）是四个不同事实。版本号更高、文件进入 `main`、Tag 已创建或 Public Core 已发布，均不会单独使治理自动生效，也不会自动替换任何 Personal Instance 当前采用的治理。

## 2. Lifecycle Status（生命周期状态）

Public Core 治理文件只使用以下正式生命周期状态：

### 2.1 `candidate`（候选）

`candidate` 表示内容正在提出、提取、审查或验证，尚未取得正式治理效力。

- 可以接受审计、讨论和修改；
- 必须明确标注其候选状态与目标版本；
- 不得覆盖当前 `active` 版本的效力；
- 可以存在于工作分支、Pull Request（合并请求）或 `main`，但不得因此被解释为已批准；
- 不得使用 Active Governance Tag（正式治理标签）宣布发布；
- AI Agent（AI 代理）可以准备和审查候选，但不能自行批准或激活候选。

### 2.2 `active`（生效）

`active` 表示对应作用域内当前正式采用的 Public Core 治理版本。

一个版本只有同时满足以下条件后才可视为 `active`：

1. 已完成规定的 Review（审查）与明确的人类 Approval（批准）；
2. 治理文件中的 `status`、`version` 与 `updated` 已在 Activation Commit（生效提交）中确定；
3. Activation Commit 已创建与版本完全对应的不可变 Governance Tag（治理标签）；
4. Commit、Tag、文件内容和批准记录已经完成远程一致性验证。

同一治理作用域在同一发布线上只能有一个 Current Active Version（当前生效版本）。Public Core 版本生效不代表任何 Personal Instance 自动采用；实例采用仍需由该实例的 System Owner（系统所有者）独立审查、批准、记录和验证。

### 2.3 `deprecated`（弃用）

`deprecated` 表示某个曾经发布的治理版本已不再作为当前推荐或当前生效版本使用，但仍需保留其历史、证据和回退价值。

- 必须记录弃用原因、替代版本、生效日期、兼容性影响及迁移或回滚路径；
- 不得移动、覆盖或复用原有 Tag 来伪造历史；
- 不得静默删除仍具有追溯、审计或恢复价值的历史版本；
- 历史 Tag 中的文件内容保持不可变，弃用事实应记录在后续发布记录或 Release Notes（发布说明）中；
- 某个 Personal Instance 是否停止使用该版本，必须由实例自身独立处理，不因 Public Core 弃用而自动改变。

从未正式生效的候选被撤回时，不需要伪装为 `deprecated`；应保留必要的审查结论，或按普通候选清理流程关闭。

## 3. Governance Version（治理版本）

治理版本采用 `MAJOR.MINOR` 或 `MAJOR.MINOR.PATCH` 格式，并与治理文件 YAML（文件顶部结构化属性）中的 `version` 完全一致：

- `MAJOR`：改变最高治理层级、用户主权、授权边界、隐私边界、Core / Personal 分离或其他不兼容的核心语义；
- `MINOR`：在保持既有核心语义和兼容边界的前提下新增、扩展或实质细化治理能力；
- `PATCH`：不改变治理语义的勘误、表述澄清、引用修复或元数据修正。

不得把实质规则变化伪装为 `PATCH`。在 `1.0` 之前，版本仍可快速演进，但不得跳过审查、批准、审计、Tag 和生效验证。

## 4. Version Upgrade Process（版本升级流程）

治理升级按以下顺序执行：

1. **Proposal（提案）**：说明当前有效版本、修改原因、目标作用域、受影响原则和预期版本等级；
2. **Candidate Preparation（候选准备）**：将新内容保持为 `candidate`，完成去实例化与 Core / Personal / Backup 边界检查；
3. **Impact Review（影响审查）**：检查兼容性、授权、隐私、安全、第三方权益、迁移与回滚影响；
4. **Public Audit（公开审计）**：执行 Secret、Identity、Path、Device、Reference、License 与 Open Source Readability（开源可读性）检查；
5. **Human Review & Approval（人工审查与批准）**：由具备对应 Public Core 治理权限的 Authorized Maintainer（授权维护者）明确批准；
6. **Activation Commit（生效提交）**：更新版本、状态、日期和必要发布记录，保持审查内容与提交内容一致；
7. **Tag & Publish（标记与发布）**：创建对应不可变 Tag，并将 Commit 与 Tag 作为同一发布单元发布；
8. **Remote Verification（远程验证）**：核对远程 Commit SHA、Tag 目标、文件版本、状态和发布记录；
9. **Adoption Review（采用审查）**：Personal Instance 如需采用，另行完成差异审查、授权、激活与验证。

任一步骤失败时，新候选不得替代当前 `active` 版本。发布动作只完成一部分时，应视为 Incomplete Release（未完成发布），优先停止生效声明、保留证据并恢复到可审查状态。

## 5. Git Tag Mapping（Git 标签对应规则）

正式治理标签统一使用：

`governance-v<Governance Version>`

示例：

- Governance Version `0.1` → Git Tag `governance-v0.1`
- Governance Version `1.2.1` → Git Tag `governance-v1.2.1`

必须遵守：

- Tag 中的版本必须与 Activation Commit 内治理文件的 `version` 完全一致；
- Tag 必须直接指向完成该版本激活的 Commit；
- `candidate` 不得使用正式 `governance-v*` Tag；
- 已发布 Tag 不得强制移动、覆盖或复用；
- 一个治理版本只能对应一个正式 Governance Tag；
- 通用软件版本 Tag 与治理 Tag 必须通过 `governance-v` 前缀区分；
- 只有完成远程 Commit 与 Tag 一致性验证后，才能宣布该版本正式发布。

如果已发布 Tag 存在错误，应通过新的修正版本、Commit 和 Tag 处理，不得改写原 Tag。若 Tag 或历史中意外包含 Secret（秘密值）或其他高风险敏感信息，应立即进入安全事件流程，优先撤销或轮换凭据，并按最小暴露原则处理历史；该安全例外不得被用于普通历史重写。

## 6. Review & Approval（审查与批准）

Authorized Maintainer 是对特定 Public Core 治理作用域具有明确发布审批权限的人类维护角色。Repository Write Access（仓库写入权限）、账号登录、AI 能力或完成技术审查本身，不自动等于治理批准权限。

审查至少确认：

- 修改内容与上级 Global Governance 一致；
- 未引入私人实例身份、账号、设备、路径、项目数据或运行状态；
- 未扩大 AI、维护者、贡献者或外部服务的默认权限；
- 版本等级与实际语义变化匹配；
- 引用、依赖、许可证、迁移和回滚路径完整；
- 公开内容可由普通开源使用者理解；
- 审查对象与最终 Activation Commit 内容一致。

批准必须是 Explicit Human Authorization（明确人工授权），并至少留下目标版本、审查范围、批准角色、批准时间和对应 Commit 的可追溯证据。AI Agent 可以提出建议、生成候选、执行审计与整理证据，但不得把自己的检查结果当作人工批准。

## 7. Rollback（回滚）

Rollback 的目标是恢复已知安全语义，同时保留公开历史和纠错链。

默认流程为：

1. 暂停有问题版本的继续采用或扩散；
2. 确认故障范围、受影响原则和最近已知安全版本；
3. 通过新的 Commit 恢复安全内容，不对 Public `main` 执行 Silent Rewrite（静默改写）或强制回退；
4. 根据实际变化创建新的治理版本，重新完成审查、批准、Tag 与远程验证；
5. 在后续发布记录中标记被替代版本及其弃用原因、替代版本和迁移说明；
6. 各 Personal Instance 独立决定是否以及如何回滚，并保留实例自身的授权与验证证据。

回滚不得通过移动旧 Tag、删除审计证据或把历史修改成“从未发生”来完成。若问题涉及凭据泄露、法律义务或其他持续重大风险，可以先采取更严格、可逆的紧急保护措施；任何长期治理变更仍需回到正常审查与批准流程。

## 8. Minimum Release Evidence（最小发布证据）

每次治理发布至少应能够追溯：

`previous_version → change_reason → review_scope → approval_role → activation_commit → governance_tag → remote_verification → successor_or_rollback_basis`

没有完整证据时，治理文件应保持 `candidate`；如发布只完成一部分，应另行记录 Incomplete Release（未完成发布）事实，不得仅凭文件内容、Commit、Tag 或口头声明宣布 `active`。

## 9. Current Status（当前状态）

本文件当前为 Public Core v0.1 `candidate`。它建立治理版本框架，但在完成审查、批准、Commit、Tag 与远程验证前不具有正式 Public Core 治理效力。
