# XINGSHU Knowledge Bridge Architecture（星枢知识桥接架构）

> Status: `design-proposal`
>
> Governance effect: `none`
>
> Runtime effect: `none`
>
> Implementation status: `not-implemented`
>
> 本文定义长期集成方向，不激活任何新能力，不改变 Personal Instance，也不宣称本文提及的 AI 产品已经全部兼容。

## 1. North Star（长期目标）

XINGSHU 的长期目标不是绑定某一个知识库，也不是绑定某一家 AI。

它希望建立一个由用户控制的中间层，使知识可以在不同 Knowledge Source（知识源）与不同 AI Client（AI 客户端）之间安全、可验证、可迁移地复用：

```text
Knowledge Sources
Obsidian / local folders / cloud drives / databases / other sources
        │
        ▼
Source Adapters（知识源适配器）
        │
        ▼
┌──────────────────────────────────────┐
│            XINGSHU Runtime           │
│                                      │
│  Identity / Scope / Policy           │
│  Knowledge & Memory Governance       │
│  Retrieval / Validation              │
│  Provenance / Audit                  │
└──────────────────┬───────────────────┘
                   │
                   ▼
Client Adapters / Protocol Gateways
MCP / Tool API / CLI / platform adapters
                   │
        ┌──────────┼──────────┐
        ▼          ▼          ▼
      Codex     ChatGPT    WorkBuddy ...
```

一句话定义：

> **知识库可以换，AI 可以换；知识的治理、来源、权限和可迁移性由 XINGSHU 保持。**

这意味着 XINGSHU 应追求 `source-neutral`（知识源中立）与 `provider-neutral`（AI 提供商中立），而不是承诺“无条件兼容所有知识库和所有 AI”。

## 2. Compatibility Definition（兼容性的准确含义）

“任意知识库接入任意 AI”应解释为：

- 任何能够通过文件、API、数据库、导出格式或其他明确接口被安全访问的 Knowledge Source，可以通过 XINGSHU Source Adapter 接入；
- 任何能够消费 MCP、Tool API、CLI、Plugin/App 或其他受支持扩展接口的 AI Client，可以通过 XINGSHU Client Adapter 接入；
- 对完全封闭、没有扩展接口、不能访问本机或不能访问远程工具的产品，XINGSHU 不保证直接兼容。

因此，兼容性由 **capability（能力）** 决定，而不是由品牌名称决定。

## 3. Core Architectural Decision（核心架构决策）

XINGSHU 将知识源侧和 AI 客户端侧解耦。

### 3.1 Source Side（知识源侧）

每一种知识来源由一个 Source Adapter 负责。

```text
Obsidian Vault ──► Filesystem / Obsidian Adapter
Google Drive  ──► Google Drive Adapter
Notion        ──► Notion Adapter
Local Folder  ──► Filesystem Adapter
Database      ──► Database Adapter
```

Source Adapter 的职责是“安全读取来源”，而不是替代 XINGSHU 的治理层。

建议的最小只读契约：

```text
discover(scope)
stat(item)
read(item)
list(scope)
```

可选能力：

```text
search(query)
watch(scope)
write(item)       # 默认禁用；未来需独立治理授权
```

所有 Source Adapter 都必须保留原始来源标识和 Provenance（溯源信息）。

## 4. XINGSHU Runtime as the Stable Middle Layer（稳定中间层）

Source Adapter 不直接把数据暴露给 AI。

请求应经过 XINGSHU Runtime：

```text
AI request
   │
   ▼
Client Adapter
   │
   ▼
Scope / Permission Check
   │
   ▼
Retrieval
   │
   ▼
Knowledge / Memory Governance
   │
   ▼
Provenance Validation
   │
   ▼
Minimum Necessary Context
   │
   ▼
AI Client
```

Runtime 至少负责：

- Scope（允许访问的范围）；
- Permission（权限）；
- Retrieval（检索）；
- Knowledge / Memory boundary（知识与记忆边界）；
- Provenance（来源与溯源）；
- Validation（验证）；
- Audit（审计）；
- Minimum disclosure（最小必要披露）。

AI 不应绕过 Runtime 直接读取整个私人知识库。

## 5. Knowledge Normalization（知识归一化）

不同知识源有不同的数据结构。XINGSHU 不应要求所有来源先迁移成同一种应用格式，而应在 Runtime 中建立稳定的规范化视图。

建议的最小统一字段：

```text
source_id
source_type
item_id
relative_or_canonical_location
title
content_type
modified_at
content_hash
provenance
access_scope
```

当来源内容需要进入 XINGSHU Knowledge Object / Memory governance 时，再映射到现有 Knowledge Object Model，而不是把所有原始文件自动转换为长期记忆。

原则：

> **Source data is not automatically XINGSHU Memory.**

原始资料、可检索知识和长期记忆必须保持语义分离。

## 6. Retrieval Strategy（检索策略）

第一阶段优先使用简单、可解释、可本地验证的方案：

```text
Metadata + deterministic scan
        ↓
Local full-text search
        ↓
Optional semantic retrieval
        ↓
Optional hybrid retrieval
```

第一版不要求云端 Embedding、外部 Vector Database 或自动摘要。

语义检索只有在真实使用证明全文检索不足时才应引入，并继续遵守来源、权限和可验证性要求。

## 7. AI Client Side（AI 客户端侧）

XINGSHU 不为每一家 AI 重写完整知识系统，而通过 Client Adapter / Protocol Gateway 暴露稳定能力。

建议的最小只读工具语义：

```text
xingshu.search(query, scope, filters?)
xingshu.get(item_id)
xingshu.status()
```

后续可增加：

```text
xingshu.get_context(...)
xingshu.get_project(...)
xingshu.validate(...)
```

写入类能力必须是独立阶段，不应与第一版只读检索同时开放。

## 8. MCP Position（MCP 的位置）

MCP（Model Context Protocol）是 XINGSHU 当前优先考虑的 AI 侧标准协议，但不是唯一接口。

```text
                 XINGSHU Runtime
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
       MCP Gateway   Tool API     CLI/stdio
          │            │            │
       MCP Clients   API Clients   Local Clients
```

采用 MCP 的原因：

- 开放协议；
- 已被多个 AI / Agent 产品采用；
- Tool contract 清晰；
- 比为每一家模型重复设计私有协议更容易维护。

但 XINGSHU 的核心契约不得依赖 MCP 独有概念。若某个平台不支持 MCP，但支持可靠的 Tool API 或其他扩展机制，应通过对应 Client Adapter 接入。

参考：

- MCP 2026-07-28 Specification: https://blog.modelcontextprotocol.io/posts/2026-07-28/

## 9. Skill Position（Skill 的位置）

Skill 不应作为 XINGSHU 的数据库、Runtime 或数据传输层。

Skill 的职责是告诉 AI：

- 什么时候应该查询 XINGSHU；
- 什么信息不得凭模型记忆猜测；
- 如何选择查询范围；
- 如何处理来源冲突；
- 什么情况下不得写入长期记忆；
- 如何使用 XINGSHU 返回的 Provenance。

因此：

```text
Skill = AI behavior / workflow instructions
MCP or API = transport / tool connection
XINGSHU Runtime = policy + retrieval + governance
Knowledge Source = user-controlled data
```

Skill 可以增强体验，但不能替代 Runtime 和数据连接层。

## 10. Obsidian as the First Source Adapter（Obsidian 作为首个知识源）

Obsidian 适合作为第一阶段验证 Knowledge Source。Vault 本质上由文件夹和子文件夹组成，Markdown 文件可以在不要求先开发 Obsidian Plugin 的情况下读取。

第一版推荐：

```text
Obsidian Vault
      │
      │ explicit allowlist + read only
      ▼
Filesystem Source Adapter
      │
      ▼
XINGSHU Runtime
```

第一阶段必须：

- 显式指定 Vault；
- 只读；
- 默认排除 `.obsidian`；
- 防止 path traversal；
- 防止 symlink escape；
- 不删除、不移动、不重命名、不修改原文件；
- 索引、缓存、数据库和日志不得写入 Vault；
- 保留相对路径、修改时间、内容 hash 与来源记录。

Obsidian Plugin 属于未来 UX（用户体验）层，不是底层接入的前置条件。

参考：

- Obsidian Vault developer documentation: https://docs.obsidian.md/Plugins/Vault

## 11. Current AI Integration Targets（当前 AI 接入目标）

以下是设计目标，不等于已经实现。

| AI / Agent | 当前已知扩展路径 | XINGSHU 策略 |
|---|---|---|
| Codex | MCP / plugin / skill ecosystem | 第一优先只读验证客户端 |
| WorkBuddy | 官方支持 MCP 与自定义 Skills | 适合作为第二类 MCP 客户端验证 |
| ChatGPT | Apps / remote MCP，能力受套餐与产品模式约束 | 条件式目标；不得假设本地 MCP 可直接连接 |
| 豆包及字节系 Agent 产品 | 豆包/火山/扣子/TRAE 生态存在 MCP 与工具扩展能力，但不同产品入口能力不完全相同 | 按具体产品能力做 Adapter，不宣称消费端豆包 App 无条件兼容 |
| Other AI Clients | MCP / Tool API / CLI / Plugin 等 | 通过 capability detection 决定接入方式 |

截至 2026-08-30 的公开参考：

- OpenAI Apps / MCP: https://help.openai.com/en/articles/11487775
- OpenAI Developer mode and MCP apps: https://help.openai.com/en/articles/12584461
- OpenAI Plugins in ChatGPT and Codex: https://help.openai.com/en/articles/20001256
- Tencent WorkBuddy MCP documentation: https://www.workbuddy.ai/docs/zh/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/MCP-Guide
- WorkBuddy product positioning (MCP + Skills): https://copilot.tencent.com/work/

平台能力会变化，因此正式兼容性必须通过运行时 Capability Test（能力测试）确认，而不是仅凭产品名称或历史文档确认。

## 12. Compatibility Tiers（兼容等级）

### Tier A — Native MCP Client

原生支持所需 MCP transport / authorization / tools。优先接入。

### Tier B — Tool / App API Client

不完整支持 MCP，但允许外部 Tool API、App 或 Plugin。通过 Client Adapter 接入。

### Tier C — Local CLI / Automation Client

没有标准 Tool API，但允许本地 CLI、stdio 或受控自动化。可以建立受限 Adapter，但必须单独评估安全性。

### Tier D — Closed Client

没有可用扩展接口。XINGSHU 不宣称直接兼容。

## 13. Security and Privacy Invariants（安全与隐私不变量）

无论接入多少知识源和 AI，以下原则不得因“方便”而绕过：

1. `read-only-first`：第一阶段默认只读；
2. `fail-closed`：不明确的权限、路径或来源默认拒绝；
3. `least-privilege`：每个 Adapter 只获得完成任务所需最低权限；
4. `least-disclosure`：只向 AI 返回回答当前问题所需的最小上下文；
5. `provenance-first`：返回内容必须能够追溯来源；
6. `no-secret-in-public-core`：私人路径、身份、Token、Vault 内容不得进入 Public Core；
7. `no-automatic-memory-promotion`：普通知识命中不得自动升级为长期记忆；
8. `auditable`：重要查询、授权和未来写入必须能够审计；
9. `portable`：知识源或 AI 客户端替换时，不应迫使用户重建全部治理结构。

## 14. Recommended Pilot Sequence（推荐验证顺序）

| Phase | 目标 | Public capability claim |
|---|---|---|
| B0 | Private Bridge Lab 隔离实验 | No |
| B1 | Source Adapter contract | No |
| B2 | Obsidian / filesystem read-only adapter | No |
| B3 | 本地全文索引与 `search/get` | No |
| B4 | Runtime retrieval contract | No |
| B5 | Read-only MCP Gateway | No |
| B6 | Codex 真实查询验证 | No |
| B7 | 第二 AI 客户端验证（例如 WorkBuddy） | No |
| B8 | Skill / workflow instruction prototype | No |
| B9 | 连续真实使用与错误案例收集 | No |
| B10 | 第二 Knowledge Source Adapter 验证 | No |
| B11 | 去个人化、脱敏、抽象与独立复审 | No |
| B12 | 决定是否形成后续 Public Candidate | Only after review |

关键 Gate：

> 在至少两个不同 AI 客户端通过同一个 XINGSHU Runtime 获取一致、可溯源的知识结果，以及至少两个不同 Knowledge Source 可以通过统一 Source Adapter Contract 工作之前，不应声称已经证明“跨知识库 / 跨 AI”的通用架构。

## 15. Minimum Meaningful Success（最小有意义成功）

第一阶段：

```text
Obsidian knowledge
      ↓
XINGSHU read-only retrieval
      ↓
Codex
```

Codex 能回答一个只能从 Personal Instance 中找到答案的真实问题，同时返回：

- source / path；
- last modified metadata；
- matched excerpt；
- provenance；
- no unauthorized file access；
- zero write to the source Vault。

第二个里程碑：

```text
Same Knowledge Source
        ↓
    XINGSHU
     ↙   ↘
 Codex   WorkBuddy(or another compatible client)
```

两个 AI 客户端获得一致的可溯源结果。

第三个里程碑：

```text
Obsidian ─┐
          ├─► XINGSHU ─► same client contract
Source B ─┘
```

证明更换知识源不需要重写 AI 侧工作流。

## 16. Non-Goals（当前非目标）

本设计当前不要求：

- 将 XINGSHU 整体做成一个 Skill；
- 将全部私人知识迁移到 XINGSHU 自有数据库；
- 自动把所有文档转换为 Memory；
- 一开始就使用向量数据库；
- 一开始就开放 AI 写入知识库；
- 为每一家 AI 单独维护一套核心逻辑；
- 声称所有 AI App 都已兼容；
- 声称所有知识库都可无条件接入。

## 17. Product Direction（未来产品形态）

若底层链路经过真实验证，普通用户最终看到的可以是：

```text
Choose knowledge sources
☑ Obsidian
□ Google Drive
□ Notion
□ Local Folder

Choose AI clients
☑ Codex
☑ WorkBuddy
□ ChatGPT
□ Other compatible client

XINGSHU
● Runtime healthy
● Sources indexed
● Permissions valid
● Provenance available
```

安装体验可以由 Plugin、App、Skill、Obsidian Plugin 或桌面控制面板包装，但这些都是上层 UX。

稳定核心始终是：

```text
Source Adapters
      ↓
XINGSHU Runtime + Governance
      ↓
Protocol / Client Adapters
```

这也是 XINGSHU 长期保持用户数据主权和平台可迁移性的基础。
