# XINGSHU Core（星枢开源核心）

XINGSHU Core 是 XINGSHU 2.0 的 Open Source Core（开源核心），用于承载平台无关、实例无关且可公开复用的治理原则、稳定契约与基础结构。

## 项目简介

XINGSHU 致力于建立一套以用户主权、最小权限、隐私保护、可验证运行和长期可迁移性为基础的 AI Governance（人工智能治理）框架。Core 关注能够服务不同 System Owner（系统所有者）的公共能力，不绑定特定个人、设备、账号、路径或私人项目。

长期产品定位上，XINGSHU 不以“新的知识库”或“新的项目管理系统”为目标。它更接近一个由用户控制的 AI Context / Memory / Habit / Governance Layer（上下文 / 记忆 / 习惯 / 治理层）：长期记住用户真正稳定的偏好、习惯与治理规则，并在需要时从用户原有的项目和知识来源中解析当前上下文，再提供给兼容 AI。

## 开源核心定位

本仓库用于维护：

- 平台无关的公共治理原则；
- Core、Schema 与 Adapter Contract（适配器契约）的稳定语义；
- 可公开复用的模板、文档和基础实现；
- 有助于安全集成不同 AI、工具与服务的开放接口。

本仓库不存放个人身份、设备档案、账号状态、认证材料、私人画像、项目数据或运行记录。

## Core 与 Personal Instance

- Core（公开核心）：公开、通用、可复用，不包含实例绑定数据。
- Personal Instance（私人实例）：由每位 System Owner 独立维护，承载其身份、设备、账号、项目、偏好和运行状态。
- Backup（备份）：只用于恢复与审计，不与 Core 或 Personal Instance 竞争 Source of Truth（唯一正式来源）。

详细边界参见 [CORE_PERSONAL_BOUNDARY.md](CORE_PERSONAL_BOUNDARY.md)。

## 当前阶段

本分支包含 XINGSHU-Core v0.4 Runnable Core / Validator CLI Candidate（可运行核心 / 验证器命令行候选）。它在完整保留 v0.2 State Separation（状态分离）、Evidence Lifecycle（证据生命周期）、Evidence-Proportional Adoption Policy Candidate（证据比例采用策略候选）与 Pre-Execution Assessment Contract（执行前评估契约），以及 v0.3 Knowledge / Memory（知识 / 记忆）候选能力的基础上，新增只读运行时验证层：

- Memory Distillation（记忆提炼）与事件触发复审；
- Knowledge Object Model（知识对象模型）的 `main / appendix / provenance` 角色；
- Migration Provenance（迁移溯源）以及迁移完成与运行验证分离；
- 三个 v0.3 JSON Schema、可复制模板、合成失败夹具和匿名迁移案例。
- 使用现有 `schemas/v0.3/` 的严格 Schema Registry、RFC 3339 `date-time` FormatChecker、语义验证器和 `xingshu` CLI；该层只读取输入，不写回、不联网、不执行外部动作。

所有 v0.2、v0.3 与 v0.4 能力仍为 `candidate`、默认关闭，`governance_effect: none`、`activation_state: not_active`。文件存在、测试通过、Commit、Pull Request、Tag 或 Release 都不会自动使其生效，也不会使任何 Personal Instance（私人实例）自动采用。v0.1 语义与恢复基线保持不变。

## Long-term Integration Direction（长期集成方向）

XINGSHU 正在评估一个 `thin-core + source-neutral + provider-neutral` 的 Context & Memory Bridge（上下文与记忆桥接）方向。

核心边界是：

```text
External Sources of Truth
Obsidian / Drive / Git / local files / other systems
        ↓
Source Adapters
        ↓
XINGSHU Thin Core
Memory / Habits / Governance / Context References
        ↓
Protocol / Client Adapters
        ↓
Compatible AI Clients
```

XINGSHU 不默认把完整项目、知识库和业务状态再复制一份。项目和文档继续留在原始 Source of Truth；XINGSHU 只保存长期记忆、习惯、权限、上下文路由以及必要的轻量 Context Reference（上下文引用），需要时按授权从原来源解析最新上下文。

因此：

- 项目事件通常留在项目事实源；
- 跨项目、跨 AI 的稳定习惯与偏好可以进入 XINGSHU Memory；
- “这个项目在哪里、如何安全找到”可以成为 XINGSHU Context Reference；
- 可重建索引或缓存不构成新的 Source of Truth。

Obsidian 可以作为第一个严格只读 External Source 验证；Codex 可以作为第一个 AI Client 验证。后续是否支持 ChatGPT、WorkBuddy、豆包系产品或其他 AI，必须依据各产品当时实际提供的 MCP、Tool API、Plugin/App、CLI 等能力进行 Capability Test（能力测试），而不是仅凭品牌名称宣称兼容。

该方向目前仅为 `design-proposal`，不属于 v0.4 已实现 Runtime 能力，不自动构成 v0.5，也不产生 Governance effect。

详见 [Context & Memory Bridge Architecture（上下文与记忆桥接架构）](docs/CONTEXT_MEMORY_BRIDGE_ARCHITECTURE.md)。

## Quick Start（快速开始）

1. 阅读 [Getting Started（开始使用）](docs/GETTING_STARTED.md)；
2. 选择明确的 Core 版本并确认其治理状态；
3. 建立 Explicitly Adopted Core Baseline（明确采用的核心基线）；
4. 在 Public Core 之外创建物理隔离的 Personal Instance；
5. 使用公共模板配置 Personal Overlay，并在验证后激活 Agent Entry。

候选文件、模板复制或较新的 Core 版本都不会自动激活 Personal Instance。

## Documentation Map（文档导航）

| 文档 | 职责 |
|---|---|
| [Global Governance](Global/00_GLOBAL_GOVERNANCE.md) | Public Core 最高公共治理候选 |
| [Core / Personal Boundary](CORE_PERSONAL_BOUNDARY.md) | Core、Personal Instance 与 Backup 的规范边界 |
| [Getting Started](docs/GETTING_STARTED.md) | 首次建立 Personal Instance 的使用路径 |
| [Personal Instance Model](docs/PERSONAL_INSTANCE_MODEL.md) | 私人实例、覆盖层、备份和信息流说明 |
| [Governance Versioning](docs/GOVERNANCE_VERSIONING.md) | 治理状态、版本、审查、Tag 与回滚规则 |
| [Glossary](docs/GLOSSARY.md) | 公共术语解释，不创建新规则 |
| [v0.1 → v0.2 Migration](docs/V0_1_TO_V0_2_MIGRATION.md) | 增量兼容、默认关闭与回退路径 |
| [v0.2 Change Notes](docs/V0_2_CHANGE_NOTES.md) | v0.2 候选范围、状态与不包含项 |
| [v0.3 Change Notes](docs/V0_3_CHANGE_NOTES.md) | v0.3 知识 / 记忆候选范围与兼容边界 |
| [v0.4 Change Notes](docs/V0_4_CHANGE_NOTES.md) | v0.4 只读运行时验证候选范围与兼容边界 |
| [Validator CLI](docs/CLI.md) | v0.4 只读验证器安装、命令、决定与退出码 |
| [Knowledge Object Model](Global/KNOWLEDGE_OBJECT_MODEL.md) | 主笔记、附录、溯源与派生视图边界 |
| [Migration Provenance](Global/MIGRATION_PROVENANCE.md) | 多来源迁移的映射、遗漏、冲突与状态分离 |
| [Context & Memory Bridge Architecture](docs/CONTEXT_MEMORY_BRIDGE_ARCHITECTURE.md) | 薄核心、外部事实源、记忆习惯与跨 AI 上下文桥接设计提案 |
| [ADR-0001 Source / Client Separation](docs/ADR-0001-KNOWLEDGE-SOURCE-CLIENT-SEPARATION.md) | 记录外部事实源、轻量上下文引用与 AI 客户端分离的架构决策 |
| [Schema Registry](schemas/README.md) | v0.2 与 v0.3 机器 Schema 的唯一导航入口 |
| [Test Registry](tests/README.md) | Conformance（符合性）、Compatibility（兼容性）与合成 fixtures 入口 |
| [Security Policy](SECURITY.md) | 安全报告与敏感信息边界 |
| [Contributing](CONTRIBUTING.md) | 公共贡献范围与审查流程 |

## Templates（模板）

- [XINGSHU_ROOT.template.md](templates/XINGSHU_ROOT.template.md)：Personal Instance 根标识候选；
- [AGENTS.template.md](templates/AGENTS.template.md)：Provider-neutral（能力提供方中立）的 Agent 接入候选。
- [KNOWLEDGE_ENTRY.template.md](templates/KNOWLEDGE_ENTRY.template.md)：知识对象候选；
- [MEMORY_ENTRY.template.md](templates/MEMORY_ENTRY.template.md)：记忆候选与晋升审查；
- [MIGRATION_PROVENANCE.template.md](templates/MIGRATION_PROVENANCE.template.md)：迁移映射与来源保护记录。

模板必须单向复制到独立 Personal Instance 后再完成私人配置；不得在 Public Core 模板中填写身份、设备、账号、项目或运行状态。

## Security（安全）

报告安全问题前，请阅读 [SECURITY.md](SECURITY.md)。请勿在 Issue、Pull Request、Discussion 或 Commit 中提交任何 Secret（秘密值）或私人数据。

## License（许可证）

本项目采用 [Apache License 2.0](LICENSE)。