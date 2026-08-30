# ADR-0001 — Separate External Sources from AI Clients and Preserve Source of Truth

> Status: `proposed`
>
> Date: `2026-08-30`
>
> Governance effect: `none`
>
> Implementation effect: `none`

## Context（背景）

XINGSHU 的核心定位不是知识库，也不是项目管理数据库。

它要长期承担的是用户跨 AI 的 Memory（记忆）、Habit（习惯）、Preference（偏好）、Context Routing（上下文路由）与 Governance（治理）。

与此同时，用户的项目、文档和业务记录通常已经存在于可靠的外部事实源中，例如：

- Obsidian；
- Google Drive；
- Git repositories；
- local folders；
- Notion / databases / project systems。

如果 XINGSHU 把这些内容再次复制并作为自己的正式项目数据维护，会产生两个问题：

1. XINGSHU 会逐渐变成第二个知识库 / 项目系统；
2. 原始来源与 XINGSHU 副本可能不同步，形成 competing Sources of Truth（互相竞争的事实源）。

如果再让每一个来源直接适配每一个 AI，还会形成 N × M 的集成关系。

## Decision（决策）

采用 `Thin Core + External Source of Truth + Dual Adapter` 架构。

```text
External Source of Truth
        ↓
Source Adapter
        ↓
XINGSHU Thin Core
Memory / Habits / Governance
Context References / Routing
        ↓
Client Adapter / Protocol Gateway
        ↓
AI Client
```

### 1. External Source of Truth

项目状态、完整文档、完整历史和业务数据继续由其原始系统维护。

XINGSHU 不默认复制第二份正式数据。

### 2. XINGSHU Thin Core

XINGSHU 原生保存：

- Identity；
- durable Memory；
- Habits / Preferences；
- Governance / Permissions；
- Context Routing；
- Provenance policy；
- Lightweight Context References。

对外部项目和知识，XINGSHU 优先保存“在哪里、如何取、谁能看、多久需要重新验证”，而不是保存全部内容。

### 3. Source Adapter

负责安全读取外部事实源，并保留其 provenance 与 Source of Truth 地位。

### 4. Client Adapter

负责把 XINGSHU 稳定能力映射到 MCP、Tool API、Plugin/App、CLI 或其他 AI 扩展接口。

## Why（理由）

### A. Avoid duplicate state（避免重复状态）

例如项目完整状态继续留在 Obsidian / Git；XINGSHU 只保存 Context Reference。

来源发生变化后，AI 查询时重新解析最新授权来源，而不是读取过期的 XINGSHU 项目副本。

### B. Keep XINGSHU lightweight（保持星枢轻量）

星枢的长期价值来自“记住用户和如何调用上下文”，而不是存储所有用户文件。

### C. Preserve the original XINGSHU purpose（保持初心）

项目事件和业务数据不等于长期记忆。

例如：

- “项目今天完成 B3” → 项目事实源；
- “用户不希望低风险操作反复确认” → XINGSHU Habit / Memory；
- “这个项目的正式状态在某路径” → XINGSHU Context Reference。

### D. Reduce integration complexity（降低集成复杂度）

通过 Source Adapter 与 Client Adapter 分离，将 N × M 直接集成压缩成：

```text
N Source Adapters + M Client Adapters
```

### E. Maintain portability（保持可迁移）

更换 AI 不要求迁移知识库；更换知识库也不要求重建用户的长期记忆与习惯治理。

## Context Reference Principle（上下文引用原则）

对于外部来源，XINGSHU 应优先保存轻量引用：

```text
reference_id
context_type
canonical_name
source_id
source_locator
access_scope
provenance_policy
freshness_policy
last_verified_at
retrieval_hint
```

默认不保存：

```text
full_project_content
full_document_copy
full_history
large_attachments
```

允许建立可重建的索引或缓存，但它们不是 Source of Truth，必须可以删除并从原来源重建。

## Consequences（后果）

### Positive

- XINGSHU 不会演变为第二个 Obsidian；
- 项目状态不需要手动双向同步；
- 过期副本风险降低；
- Runtime 可以保持小而稳定；
- Memory / Habit 与 Project Event 的语义边界更清楚；
- 每个来源与每个 AI 可以独立适配、授权和撤销；
- 有利于 Local-first、Read-only-first 与用户数据主权。

### Trade-offs

- 查询外部项目状态时需要实时或按需读取来源；
- 必须定义 freshness policy；
- 来源不可用时，XINGSHU 可能只能返回最后验证状态或明确的 unavailable；
- 为提高性能可能需要缓存，但缓存必须可重建且不能升级为事实源；
- 后续写入外部来源时需要更严格的授权与审计。

## Rejected Alternatives（未采用方案）

### A. XINGSHU stores every project state

拒绝。

会造成状态复制、同步成本和过期风险，并让 XINGSHU 偏离记忆与习惯中枢定位。

### B. Treat every project event as Memory

拒绝。

一次项目进展通常是业务事件，不具备跨时间、跨 AI 的长期记忆价值。

### C. Import the whole Obsidian Vault into XINGSHU

拒绝作为默认架构。

Obsidian 可以继续作为原始事实源；XINGSHU 只按授权读取并建立必要索引 / 引用。

### D. Every AI reads every source directly

拒绝作为长期架构。

会产生 N × M 维护问题，并让权限、来源和治理逻辑散落在各 AI 客户端。

### E. Make the whole XINGSHU a Skill

拒绝。

Skill 适合行为和工作流说明，不应承担记忆存储、权限治理、数据连接和来源验证。

### F. MCP-only architecture

拒绝。

MCP 可以优先使用，但 XINGSHU 核心契约应保持协议中立。

## Validation Criteria（验证标准）

该架构只有在真实实验满足以下条件后，才有资格进一步提升：

1. XINGSHU 可以只保存一个轻量 Context Reference，而项目本体继续保留在原事实源；
2. 一个来源更新后，AI 下一次查询能得到新的来源结果，不要求同步 XINGSHU 项目副本；
3. 一个 AI Client（首选 Codex）可以通过 XINGSHU 获取来源可验证结果；
4. 第二个 AI Client 可以复用同一 XINGSHU Runtime contract；
5. 第二个 External Source 可以复用同一客户端契约；
6. 所有实验保持 Personal Data 与 Public Core 边界。

## Related Document

- [XINGSHU Context & Memory Bridge Architecture](CONTEXT_MEMORY_BRIDGE_ARCHITECTURE.md)
