# ADR-0001 — Separate Knowledge Sources from AI Clients

> Status: `proposed`
>
> Date: `2026-08-30`
>
> Governance effect: `none`
>
> Implementation effect: `none`

## Context（背景）

XINGSHU 希望长期支持：

- 多种 Knowledge Source（知识源），例如 Obsidian、本地文件夹、云盘、Notion、数据库；
- 多种 AI Client（AI 客户端），例如 Codex、ChatGPT、WorkBuddy，以及其他具备可用扩展接口的 AI / Agent 产品。

如果让每一个知识库直接适配每一个 AI，会形成 N × M 的集成关系：

```text
Obsidian → Codex
Obsidian → ChatGPT
Obsidian → WorkBuddy
Drive    → Codex
Drive    → ChatGPT
Drive    → WorkBuddy
...
```

随着知识源和 AI 数量增加，维护复杂度、权限控制、行为差异和隐私风险都会快速上升。

## Decision（决策）

采用双适配器分层：

```text
Knowledge Source
      ↓
Source Adapter
      ↓
XINGSHU Runtime
      ↓
Client Adapter / Protocol Gateway
      ↓
AI Client
```

### Source Adapter

只负责把来源安全地映射为 XINGSHU 可治理、可检索、可溯源的数据视图。

### XINGSHU Runtime

作为稳定中间层，集中负责权限、范围、知识/记忆边界、检索、验证、来源和审计。

### Client Adapter

只负责将 XINGSHU 的稳定工具契约映射到特定 AI 所支持的 MCP、Tool API、Plugin/App、CLI 或其他扩展接口。

## Why（理由）

该方案将理论上的 N × M 集成问题压缩为：

```text
N Source Adapters + M Client Adapters
```

而不是：

```text
N × M direct integrations
```

它同时带来以下好处：

1. 更换 AI 不要求重新迁移知识库；
2. 更换知识库不要求重写 AI 侧工作流；
3. 权限与隐私控制集中在 XINGSHU，而不是散落在多个客户端；
4. Provenance（溯源）可以保持统一；
5. MCP 可以作为优先协议，但不会成为核心架构的单点依赖；
6. Skill 可以负责 AI 行为说明，而不会被误用为数据层；
7. 有利于后续开源维护和第三方 Adapter 贡献。

## Consequences（后果）

### Positive

- 架构更容易扩展；
- Provider-neutral 与 Source-neutral 目标更明确；
- 更适合 Local-first / Read-only-first；
- 公共 Core 不需要保存私人数据；
- 每个 Adapter 可独立测试、独立授权、独立撤销。

### Trade-offs

- 初期需要先定义稳定 Adapter Contract；
- 不同来源仍需要编写不同 Adapter；
- 完全封闭的 AI 产品依然无法保证兼容；
- 跨平台协议能力会变化，需要 Capability Test，而不能只维护静态品牌名单；
- 若未来增加写入能力，需要比只读检索更严格的授权与审计机制。

## Rejected Alternatives（未采用方案）

### A. 把整个 XINGSHU 做成一个 Skill

拒绝。

Skill 适合行为说明和工作流，不应承担知识存储、权限治理和数据传输职责。

### B. 为每个 AI 直接读取 Obsidian

拒绝作为长期架构。

这会让权限、路径、检索和来源逻辑重复散落在不同 AI 客户端，并增加数据暴露面。

### C. 强制把所有知识迁移到 XINGSHU 自有数据库

拒绝作为前置要求。

XINGSHU 应优先允许用户保留原始 Source of Truth，并通过 Adapter 提供规范化视图；只有明确需要时才生成受治理的派生对象。

### D. MCP-only architecture

拒绝。

MCP 是优先协议，但长期架构应以稳定工具语义为核心，并允许 Tool API、CLI 或平台特定 Adapter 作为兼容路径。

## Validation Criteria（验证标准）

该决策只有在真实实验中满足以下条件后，才有资格进一步提升为实现级架构：

1. 一个 Knowledge Source（首选 Obsidian）可通过 Source Adapter 严格只读检索；
2. 一个 AI Client（首选 Codex）可通过 XINGSHU 返回可溯源结果；
3. 第二个 AI Client 可在不重写 Source Adapter 的情况下使用同一结果契约；
4. 第二个 Knowledge Source 可在不重写 AI Client Adapter 的情况下接入；
5. 所有实验保持 Personal Data 与 Public Core 的边界。

## Related Document

- [XINGSHU Knowledge Bridge Architecture](KNOWLEDGE_BRIDGE_ARCHITECTURE.md)
