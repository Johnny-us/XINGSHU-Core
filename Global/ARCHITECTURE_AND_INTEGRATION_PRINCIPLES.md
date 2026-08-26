---
type: global-policy
system: xingshu-2.0
scope: public-core
status: candidate
version: 0.1
updated: 2026-08-25
governed_by: Global/00_GLOBAL_GOVERNANCE.md
visibility: public
---

# Architecture & Integration Principles（架构与集成原则）

> 本文件约束 XINGSHU Public Core（星枢公共核心）应该自己实现什么、应该接入什么，以及如何避免为了功能数量重复建设。它继承 [Global Governance（全局治理总纲）](00_GLOBAL_GOVERNANCE.md)，不改变其中的用户主权、权限、隐私、专业责任、重大影响与 Core / Personal / Backup（核心 / 私人实例 / 备份）边界。

## 1. Build vs Integrate（自研与集成）

XINGSHU 不以复制通用模型、通用 Agent Builder、通用 Memory Engine、通用 RAG、浏览器自动化或其他已有成熟基础能力作为默认目标。对于已经存在、质量更高、维护更活跃且能够满足治理要求的能力，默认优先通过稳定接口进行 Integrate（集成），而不是重复实现。

这不是“禁止自研”。出现以下任一情况时，可以设计或实现 XINGSHU 自己的组件：

- 现有方案无法满足 User Adaptation（用户适配）或 Context（上下文）要求；
- 现有方案无法满足 Governance（治理）、Privacy（隐私）、数据权利、专业责任或安全边界；
- 现有方案造成不可接受的 Vendor Lock-in（厂商锁定），或无法迁移用户关键资产；
- 现有方案对普通用户暴露过多技术复杂度，且无法通过适配层可靠解决；
- 可靠性、离线、成本、性能、许可证或长期维护条件无法满足实际需求；
- XINGSHU 需要定义一个跨实现的稳定 Contract（契约 / 接口），而现有生态没有可复用标准。

## 2. Capability Provider Neutrality（能力提供方中立）

模型、Agent、Memory、RAG、工具、插件、设备与云服务都应被视为 Capability Provider（能力提供方）或实现组件，而不是 XINGSHU 本体。

- 不因当前某一家最强，就把其产品名写死成永久 Core 语义；
- 角色、权限、用户上下文与治理规则应尽量独立于具体 Provider；
- 新 Provider 能提供更好的结果时，可以通过验收后替换或并存；
- Provider 替换不得静默扩大权限，也不得把平台自身 Memory 当作用户正式长期资产的唯一 Source of Truth（唯一正式来源）。

## 3. Stable Contracts Before Duplicated Features（先定义稳定接口，再复制功能）

当多个模型、Agent 或工具都能承担同类能力时，优先定义 XINGSHU 需要的输入、输出、权限、证据、失败状态与迁移要求，再选择实现。

例如，XINGSHU 更应该定义“Memory 应怎样被读取 / 写入 / 过期 / 迁移”“Execution Agent 需要怎样验收”“Domain Pack 如何声明风险与结果标准”，而不是先绑定某个具体产品的数据结构。

### 3.1 Human Configuration Contract（人类配置契约）

XINGSHU 应定义平台无关的 Human Configuration Contract（人类配置契约），用于表达“这个人希望 AI / 工具如何服务自己”，而不是直接把某一 Provider（能力提供方）的设置项当成用户本体配置。

该契约至少应能够承载与当前任务有关的：

- Role / Stage / Domain / Competence（角色 / 阶段 / 领域 / 胜任度）；
- 解释深度、术语暴露、交互方式与自动化偏好；
- 用户明确的确认边界、风险偏好与 Protected Action（受保护动作）要求；
- 画像字段的 `scope / source / observed_at / review_trigger / evidence_state`；
- 与平台无关的目标状态，而不是某个产品 UI 的具体开关名称。

Provider 自身的 Memory、自定义指令、个性化设置、Agent 配置、版本控制、Environment（环境）、Workspace（工作区）或其他工具配置，应被视为 Human Configuration Contract 的 Derived / Applied Configuration（派生 / 已应用配置），不得反向成为用户长期身份与治理的唯一 Source of Truth。

Human Configuration Contract 属于对应 Personal Instance（私人实例）的受控配置；Public Core 只定义通用契约，不保存具体用户的身份、画像、偏好或实例状态。

### 3.2 Provider Adapter Contract（能力提供方适配契约）

每个 Provider Adapter（能力提供方适配器）应把 XINGSHU 的稳定语义映射为当前平台能够真实实现的配置与动作。Adapter 至少需要声明：

- 当前 Provider / 版本可识别的能力与限制；
- XINGSHU 语义到 Provider 设置 / API / 本地工具动作的映射；
- 所需权限、数据暴露范围、失败状态与恢复方式；
- 配置读取、写入、验证与迁移能力；
- 平台变化后何时需要 Reverification（重新验收）。

Adapter 不得因为平台暂时缺少某个开关，就修改或丢失上层用户意图。平台改版、设置重命名、API 变化或 Provider 替换时，优先更新 Adapter，而不是要求用户重新建立完整画像。

### 3.3 Desired / Observed / Applied State（目标 / 观测 / 已应用状态）

配置系统应至少区分：

- `desired`：根据当前用户上下文、治理与任务得出的目标状态；
- `observed`：当前 Provider / 工具真实检测到的状态；
- `applied`：XINGSHU 最后一次成功实施并验证的状态。

不得因为“曾经写入过”就假设当前仍然生效。`desired != observed` 或 `applied != observed` 时，应按风险进入 Configuration Drift（配置漂移）检查、重新适配或重新验收。

### 3.4 Configuration Support Levels（配置支持等级）

Adapter 对每项配置应能够表达当前支持等级，至少包括：

- `automatic`：可由 XINGSHU 自动执行并验证；
- `assisted`：需要用户完成少量平台交互，但 XINGSHU 可准备步骤并验证结果；
- `recommended`：当前只能生成推荐，无法可靠读取 / 写入实际状态；
- `unsupported`：当前 Provider 不支持该能力或无法安全实现。

普通用户前台应优先看到“需要做什么 / 是否已经完成 / 是否需要确认”，而不是被迫理解 API、版本控制、Environment、Workspace 或其他底层实现名词。技术细节可以保留在 Expert / Developer View（专家 / 开发者视图）中。

### 3.5 State Separation（状态分离）

Public Core 使用 [State Separation Architecture（状态分离架构）](STATE_SEPARATION_ARCHITECTURE.md) 区分 Source、Runtime、Observed 与 Decision State。本文件只保留架构引用；状态字段、转换条件与安全默认以该专项候选与对应 Schema 为唯一实现语义。记录某个状态、命令返回成功或形成 Decision（决定），均不自动产生 Authorization（授权）、Activation（激活）或 Adoption（采用）。

## 4. Open & Composable by Default（默认开放与可组合）

在不暴露 Secret、私人数据或受保护资产的前提下，XINGSHU 应优先采用：

- 可读的数据与配置格式；
- 可替换的接口；
- 清晰的版本与来源链；
- 可单独启用、暂停、升级和退役的 Domain Pack / 组件；
- 允许社区实现不同 Provider Adapter、Domain Pack 与工具集成的扩展方式。

Open Source（开源）本身不是质量保证。任何社区组件仍需通过来源、许可证、安全、维护状态、权限与实际效果验收，不能因为“开源”就自动进入 `active`。

## 5. Upstream Progress Is Leverage（利用上游进步）

上游模型、工具、服务或开源能力增强时，XINGSHU 应优先判断“怎样让用户安全获得这些进步”，而不是把上游进步视为必须正面复制的竞争压力。

若上游已经原生解决某项 XINGSHU 过去承担的技术问题，应评估是否可以删除、简化或降级本地重复实现；XINGSHU 的长期价值应更多集中在用户连续性、动态适配、领域治理、能力编排与可迁移性，而不是维持没有必要的技术重复。

## 6. Replacement & Decommission（替换与退役）

任何被更好实现替换的组件，应完成：

`能力对照 → 权限对照 → 数据 / 状态迁移 → 真实验证 → 切换 Primary Executor（如适用） → 撤销旧权限 → 保留必要历史 → 更新 Source of Truth`

不得因为“新工具更强”就直接并行建立第二套正式执行链；也不得为了保留已有代码而阻止更合适的组件替换。

## 7. Current Status（当前状态）

本文件当前为 Public Core v0.1 `candidate`。它不包含特定用户、账号、设备、路径或实例运行状态；在完成审查、批准与发布流程前，不具有正式 Public Core 治理效力。
