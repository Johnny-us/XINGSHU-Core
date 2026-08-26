---
type: public-case-study
system: xingshu-2.0
scope: public-core
status: candidate
version: 0.3-candidate
updated: 2026-08-26
governance_effect: none
activation_state: not_active
privacy: anonymized
visibility: public
---

# NaiveBridge Knowledge Migration Case（知识迁移案例）

> 本案例由历史迁移复盘去实例化而来，只验证 v0.3 Knowledge / Memory 模型。它不包含真实路径、节点、账号、设备、身份、包名、私人环境或可执行凭据，也不证明任何当前运行环境已经配置或可用。

## 1. Case Question（案例问题）

一个技术主题分散在 11 个旧来源中，内容同时包含当前机器状态、通用部署流程、大型规则清单、历史取舍和外部依赖。如何在不改动源材料、不制造第二正式入口的前提下，形成可复用、可审查且不夸大运行状态的知识对象？

## 2. Source Inventory（来源清单）

本案例用 `source-01` 至 `source-11` 表示 11 个只读历史来源。公开案例只保留数量、类别和匿名映射，不保留真实文件名、绝对路径或正文。

| 来源组 | 数量 | 公开类别 | 处理原则 |
|---|---:|---|---|
| 核心说明 | 3 | historical_record | 合并稳定结论，保留差异 |
| 操作与恢复 | 3 | historical_record | 抽取通用流程，不复制实例路径 |
| 规则与清单 | 2 | historical_record | 进入 Appendix，不挤占主流程 |
| 迁移与变更 | 2 | provenance | 进入 Provenance，保留取舍 |
| 外部说明 | 1 | external_source | 只作来源引用，需按版本复核 |

源材料以只读方式参与提炼。迁移目标没有删除、改名、覆盖或回写这 11 个来源；`source_unchanged` 与内容迁移状态分别记录。

## 3. Target Knowledge Object（目标知识对象）

```text
NaiveBridge topic
├─ main: reusable knowledge and primary procedure
├─ appendix: large rule inventory
└─ provenance: 11-source mapping, omissions and historical decisions
```

- `main` 是唯一正式入口，保存核心结论、通用流程、关键验证、失败处理、外部依赖和附录链接；
- `appendix` 保存会淹没主流程的大型规则清单，并回链 `main`；
- `provenance` 保存 11 个来源的映射、合并 / 去重、遗漏原因和历史取舍，但不成为当前操作入口。

“完整知识”在这里表示读者可以从 `main` 完成判断并访问所有必要对象，不表示所有内容必须位于一个物理文件。

## 4. Mapping and Deduplication（映射与去重）

| 来源 | 目标 | 决定 | 理由 |
|---|---|---|---|
| `source-01`–`source-03` | `main / 核心说明` | merged | 合并重复定义，保留仍有效的共同结论 |
| `source-04`–`source-06` | `main / 通用流程与恢复` | summarized | 去除实例路径和一次性操作，只保留可复用流程 |
| `source-07`–`source-08` | `appendix / 规则清单` | copied-and-normalized | 内容规模大，但仍由主笔记提供关键摘要与入口 |
| `source-09`–`source-10` | `provenance / 历史取舍` | merged | 记录版本变化和迁移决定，不参与当前加载 |
| `source-11` | `main / 外部依赖` | referenced | 外部材料不等同于本地运行验证 |

重复段落可以省略，但每项省略都需要 `duplicate` 原因和 `covered_by_ref`。过时路径、未经核实的实例状态或私人信息只记录 Omission Reason（遗漏原因），不复制原文。

## 5. Current State vs Reusable Procedure（当前状态与可复用流程）

历史来源中描述的 Current Machine State（当前机器状态）只说明当时环境，不应迁移成跨平台命令。通用流程只保留：

- 必要前置条件与外部依赖类别；
- 平台、版本与 Environment Class（环境类别）；
- 不包含实例路径的操作顺序；
- 预期结果、验证方法、失败处理和回滚要求。

若目标平台、路径语义或版本不同，Scope 必须重新核实。旧环境中的本地路径不得被直接复用为新平台默认值。

## 6. Source Priority（来源优先级）

来源优先级按具体 Claim（主张）判断：

1. 当前运行状态由当前环境的可重复观测证明；
2. 特定版本命令由该版本的权威说明约束；
3. 通用安全边界由已采用治理与主知识对象约束；
4. 历史笔记用于追溯，不自动覆盖前三类来源。

这些优先级不能互相越权。当前观测不能自动成为通用流程，版本说明不能授予执行权限，历史文件更晚也不能仅因时间较新而成为正式来源。

## 7. External Dependencies and Command Risk（外部依赖与命令风险）

知识对象记录依赖类别、权威获取方式、最低兼容约束和缺失时处理，但不把可重新获得的外部二进制、秘密配置或登录状态复制进 Public Core。

命令或步骤按影响标记为：

- `read_only`：只读观察；
- `ordinary_change`：普通、可恢复修改；
- `privileged_change`：需要提升权限的修改；
- `high_risk_connectivity`：可能影响连接或恢复路径的高风险修改。

风险标签不是授权。高风险步骤仍需要明确 Scope、恢复点、Stop Condition（停止条件）和结果验证。

## 8. Independent Completion States（独立完成状态）

本案例的正确表达是：

```yaml
document_state: candidate
migration_state: migrated
runtime_validation_state: pending_verification
```

11 个来源已经完成公开映射与取舍，因此迁移可以是 `migrated`。但本案例没有访问或验证任何当前运行环境，因此只能是 `pending_verification`。`Migration Complete != Runtime Verified`。

## 9. Acceptance Result（验收结果）

该案例通过以下模型检查：

- 11 个来源均有映射或带原因的遗漏记录；
- `main` 是唯一正式入口，Appendix 与 Provenance 均回链；
- 当前机器状态与可复用流程分开；
- 外部依赖和命令风险被显式表达；
- 源材料保持只读，Derived View 不反写 Source；
- 迁移状态与运行验证状态分开；
- 不包含真实身份、账号、设备、路径、节点、私人环境、聊天正文或 Secret。

此结果只说明 v0.3 Candidate 模型可以表达该迁移，不是对 NaiveBridge Runtime、部署结果、采用状态或发布状态的证明。
