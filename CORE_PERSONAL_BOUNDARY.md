# Core / Personal Instance / Backup Boundary

本文定义 XINGSHU Core（公开核心）、Personal Instance（私人实例）与 Backup（备份）之间的长期数据边界。

## 1. Core（公开核心）

Core 是公开、通用、平台无关且可复用的正式核心。它可以包含：

- 公共治理原则与安全边界；
- 平台无关的 Schema（结构定义）与稳定契约；
- Provider Adapter Contract（能力提供方适配契约）；
- 可公开复用的模板、文档、测试和基础实现；
- 不依赖特定用户、设备、账号或私人项目的示例。

Core 不得包含个人身份、设备信息、账号状态、本地路径、Secret（秘密值）、私人画像、项目数据或实例运行状态。

## 2. Personal Instance（私人实例）

Personal Instance 是每位 System Owner（系统所有者）独立维护的私人运行实例，可以承载：

- 所有者身份与授权关系；
- 账号、设备、软件与环境事实；
- 私人偏好、画像、项目、任务和工作流；
- 当前 Runtime（运行时）状态与验证记录；
- 私人治理覆盖层和实例级决策。

Personal Instance 不属于公共 Core，不得因为技术上可访问就被复制、提交或同步到公开仓库。

## 3. Backup（备份）

Backup 用于恢复、审计和历史追溯。它不是活动工作区，也不因内容较新而成为 Source of Truth（唯一正式来源）。

Backup 不得直接作为公开发布来源。从 Backup 恢复的内容仍需重新完成真实性、适用性、隐私与公开权检查。

## 4. 数据边界原则

任何内容进入 Core 前，至少应完成：

`通用价值判断 → 去实例化 → 去身份化 → 去设备化 → 去账号化 → 去路径化 → Secret 扫描 → 来源与许可证检查 → Public Review（公开审查）`

必须长期保持：

- Core 不硬编码某位 System Owner；
- Personal Instance 不成为 Core 的默认数据；
- Secret 只保存在与实际架构匹配的受保护凭据系统中；
- 工作存储、同步副本和 Backup 不互相冒充；
- 公开权、访问权、版权和第三方处理权必须分别判断。

## 5. 禁止自动双向同步

Core 与 Personal Instance 之间禁止建立自动双向文件同步、目录镜像或符号链接。

允许的长期流向是：

### Core → Personal Instance

Public Core Release（公开核心版本）经过差异检查、兼容性检查和必要批准后，由 Personal Instance 明确采用。Core 的更新不得仅因版本较新就自动覆盖私人实例的当前有效治理。

### Personal Instance → Core

私人实践中产生的通用候选内容，必须先完成抽象、脱敏、来源和许可证审查，再作为独立公共候选提交。Personal Instance 原文件不得直接同步到 Core。

## 6. Source of Truth（唯一正式来源）

- Core 是公共原则、公共契约和公开实现的正式来源；
- Personal Instance 是实例身份、设备、账号、项目和运行状态的正式来源；
- Backup 只承担恢复与追溯职责；
- 三者职责不同，不建立相互竞争的可编辑正文。
