---
type: public-documentation
system: xingshu-2.0
scope: public-core
status: candidate
version: 0.1
updated: 2026-08-25
governed_by: Global/00_GLOBAL_GOVERNANCE.md
visibility: public
---

# Personal Instance Model（私人实例模型）

本文件说明 XINGSHU-Core（星枢公共核心）、Personal Instance（私人实例）与 Backup（备份）的职责、数据边界和长期流向。它解释 [Core / Personal Instance / Backup Boundary（核心、私人实例与备份边界）](../CORE_PERSONAL_BOUNDARY.md)，不建立第二套治理入口。

## 1. Core（公共规则来源）

Core 是公开、通用、平台无关且可复用内容的正式来源，可以包含：

- 通用治理原则与安全边界；
- 架构原则和稳定契约；
- 公共 Schema（结构定义）；
- Provider-neutral（能力提供方中立）的 Adapter Contract（适配器契约）；
- 可公开复用的模板、使用说明和基础实现。

Core 不得包含：

- 个人身份或私人画像；
- 账号、凭据或认证状态；
- 设备信息或本地绝对路径；
- 私人项目、任务和工作记录；
- 私人配置、实例授权或运行状态；
- Personal Instance 或 Backup 中的非公开内容。

## 2. Personal Instance（用户私人配置来源）

Personal Instance 是单个实例私人事实与配置的正式来源，可以承载：

- 实例治理主体和授权关系；
- 用户偏好、画像与交互配置；
- 账号、环境、工具与软件事实；
- 私人项目、任务、资产、工作流和工作记录；
- Runtime（运行时）状态、验证证据和实例级决策；
- 已采用 Core 之上的 Personal Overlay（私人覆盖层）。

Personal Instance 不属于 Public Core。Core 维护者、贡献者或 Agent 不会因为能够读取公共仓库而自动获得任何私人实例权限。

Personal Overlay 可以增加实例事实和更严格规则，不得静默放宽已采用 Core 的隐私、安全、授权、第三方权益与风险边界。

## 3. Backup（恢复用途）

Backup 只承担：

- 数据恢复；
- 审计与纠错；
- 必要的历史追溯。

Backup 不是活动工作区，不是默认运行来源，也不因时间较新而成为 Source of Truth（唯一正式来源）。从 Backup 恢复的内容必须重新检查完整性、真实性、适用性、权限、隐私和当前状态。

Backup 不得直接作为 Public Core 发布来源，也不得与 Core 或 Personal Instance 自动合并。

## 4. Source of Truth Separation（正式来源分离）

| 层级 | 正式负责 | 不负责 |
|---|---|---|
| Core | 公共规则、架构、治理、模板、公开说明 | 私人身份、项目、配置、运行状态 |
| Personal Instance | 实例身份、授权、配置、项目、工作记录、运行状态 | 公共 Core 的发布与社区维护 |
| Backup | 恢复、审计、历史追溯 | 日常运行、自动发布、当前治理替换 |

同一作用域内，同一类正式信息只维护一个 Source of Truth。副本、缓存、同步副本、导出文件、较新文件或 Backup 不得与正式来源竞争。

## 5. Allowed Information Flow（允许的信息流）

### Core → Personal Instance

只允许显式采用：

`选择明确版本 → 差异与兼容性检查 → 必要授权 → 单向复制或实现 → 验证 → 记录采用状态`

Core 的 Commit、Release 或 Tag 不会自动替换 Personal Instance 当前采用的治理。

### Personal Instance → Core

只允许生成独立公共候选：

`识别通用价值 → 抽象 → 去实例化 → 脱敏 → 来源与许可证检查 → Public Review → 独立候选`

Personal Instance 原文件、目录、工作记录或运行数据不得直接复制、同步或提交到 Public Core。

### Backup → Personal Instance

只允许受控恢复。恢复后必须重新验证，再决定是否成为 Personal Instance 的当前事实或配置。

Backup 不直接流向 Core。

## 6. Prohibited Coupling（禁止耦合）

Core 与 Personal Instance 之间明确禁止：

- 自动双向同步；
- 目录镜像；
- 符号链接；
- 把 Personal Instance 放入 Public Core 子目录；
- 让 Core 的版本控制自动跟踪私人文件；
- 让 Public Core 更新自动覆盖私人配置；
- 把私人数据、Secret、工作记录或运行状态带入 Public Core。

访问权、复制能力或相同工具链都不构成绕过上述边界的授权。

## 7. Personal Configuration Layer（私人配置层）

推荐的语义层次为：

`Public Core → Explicitly Adopted Core Baseline（明确采用的核心基线） → Personal Overlay → Runtime Facts（运行事实）`

- Public Core 定义公共语义；
- Adopted Core Baseline 记录实例明确采用的公共版本；
- Personal Overlay 保存实例事实和更严格规则；
- Runtime Facts 保存当前观测、应用和验证状态。

这些层次不得通过自动同步压成同一目录或同一份可编辑正文。

## 8. Boundary Verification（边界验证）

实例建立、Core 升级或恢复后，至少确认：

- Core 与 Personal Instance 位于不同工作区；
- Public Core 中没有私人身份、账号、设备、路径、项目或工作记录；
- Personal Instance 不被 Public Core 的版本控制跟踪；
- 不存在自动双向同步、镜像或符号链接；
- Backup 不承担活动运行或自动发布职责；
- 采用版本、授权、验证和回滚依据均有真实记录；
- Secret 没有进入 Markdown、日志、模板、公共仓库或普通 Backup。

任何一项无法确认时，应保持 `candidate`、`needs_review` 或其他明确的未完成状态，不得宣称边界已经生效或验证通过。
