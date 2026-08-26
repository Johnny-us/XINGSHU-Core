---
type: public-documentation
system: xingshu-2.0
scope: public-core
status: candidate
version: 0.3-candidate
updated: 2026-08-26
governed_by: Global/00_GLOBAL_GOVERNANCE.md
visibility: public
---

# Glossary（术语表）

本文件只解释 XINGSHU Public Core（星枢公共核心）中的常用术语，不创建新规则、不授予权限，也不替代正式治理。若本文件与 [Global Governance（全局治理总纲）](../Global/00_GLOBAL_GOVERNANCE.md)、[Core / Personal Boundary（核心与私人实例边界）](../CORE_PERSONAL_BOUNDARY.md) 或其他适用治理发生差异，以正式治理为准。

## Core（公共核心）

公开、通用、平台无关且可复用的规则、架构、治理、模板、文档和基础实现来源。Core 不保存任何 Personal Instance 的私人数据。

## Personal Instance（私人实例）

由单个实例独立维护的私人环境，保存该实例的身份、授权、配置、项目、工作记录和运行状态。Personal Instance 不属于 Public Core。

## Personal Overlay（私人覆盖层）

建立在 Explicitly Adopted Core Baseline（明确采用的核心基线）之上的实例配置层，用于保存私人事实和更严格的实例规则。它不能静默放宽已采用 Core 的边界。

## Backup（备份）

用于恢复、审计和历史追溯的副本或恢复资产。Backup 不是活动工作区，也不会自动成为 Source of Truth（唯一正式来源）。

## Agent（代理）

能够读取信息、生成结果或执行动作的 AI 或自动化执行组件。Agent 的能力、胜任度和授权是不同事实。

## Provider（能力提供方）

提供模型、Agent、工具、存储、检索、云服务或其他能力的可替换实现。Public Core 不把某个具体 Provider 写成永久核心语义。

## Adapter（适配器）

把 XINGSHU 的稳定语义映射到某个 Provider 或工具实际能力、配置和限制的适配层。

## Runtime（运行时）

系统或 Personal Instance 当前真实运行时的组件、配置、权限、状态和观测结果。Runtime 事实不因被记录或预期就自动成立。

## Source of Truth（唯一正式来源）

在明确作用域内负责维护某类正式信息的唯一位置。副本、缓存、聊天、较新文件或 Backup 不会仅因可访问而取得该地位。

## Least Privilege（最小权限）

只授予完成当前职责所需的最小主体、对象、数据、动作、时间和渠道范围。

## Protected Action（受保护动作）

因现实影响、数据敏感度、专业责任、第三方权益、不可逆性或其他风险，需要额外资格、授权、审查、验证或停止机制的动作。具体门禁由适用治理和领域规则确定。

## State Separation（状态分离）

将 Source（来源）、Runtime（运行）、Observed（观测）与 Decision（决定）状态分开记录的架构契约。声明、命令成功、有证据的观测与治理决定不能相互冒充。

## Evidence Metadata（证据元数据）

说明 Evidence 的对象、结论范围、来源、方法、时效、隐私处理与纠错关系的公共记录。它不包含原始 Payload（载荷）或私人位置。

## Evidence-Proportional Classification（证据比例分类）

根据证据成熟度和环境差异建议 Class 1 / 2 / 3 或 `needs_review` 审查路由的候选分类。它不是风险等级，不减少门禁，也不产生采用或授权。

## Pre-Execution Assessment（执行前评估）

在外部动作开始前，核对目标、作用域、治理、风险、隐私、可逆性、Evidence Plan、Stop Condition 与已存在外部授权的候选契约。`ready_for_execution` 不等于 Authorization。

## Capability Manifest（能力清单）

为 Consumer（消费者）提供版本、候选能力、Schema、测试、兼容和回退引用的机器可读入口。Manifest 声明不等于启用、采用、治理生效或授权。

## Memory Candidate（记忆候选）

从来源或事件中提取、但尚未完成来源核实、去重 / 冲突审查和晋升审查的候选结论。Memory Candidate 不是正式记忆，也不是聊天压缩结果。

## Conclusion State（结论状态）

表示结论处于 `candidate`、`reviewed`、`active`、`needs_review`、`superseded`、`deprecated` 或 `historical` 的知识生命周期状态。它与 Evidence State（证据状态）分开维护。

## Knowledge Object（知识对象）

围绕一个主题与作用域组织的知识单元。一个完整 Knowledge Object 可以包含一个 `main`、多个 `appendix` 和 `provenance`，但只能有一个当前正式入口。

## Document Role（文档角色）

Knowledge Object 中的职责：`main` 是唯一正式入口，`appendix` 保存大型清单或技术材料，`provenance` 保存来源、迁移、取舍与历史。附录和溯源对象不构成第二 Source of Truth。

## Derived View（派生视图）

从一个或多个 Source 生成的索引、摘要、投影或展示。Derived View 应可重新生成，不得覆盖或反向改写 Source。

## Migration Provenance（迁移溯源）

记录来源清单、映射、合并 / 去重、遗漏原因、源材料保护、冲突和目标关系的迁移元数据。它不证明运行已经验证，也不授予删除来源、执行、公开或采用权限。

## Independent Knowledge States（独立知识状态）

`document_state` 表示文档成熟度，`migration_state` 表示迁移完成度，`runtime_validation_state` 表示目标环境中的运行验证结果。三者不得互相推导；`migrated` 不等于 `verified`。
