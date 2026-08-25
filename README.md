# XINGSHU Core（星枢开源核心）

XINGSHU Core 是 XINGSHU 2.0 的 Open Source Core（开源核心），用于承载平台无关、实例无关且可公开复用的治理原则、稳定契约与基础结构。

## 项目简介

XINGSHU 致力于建立一套以用户主权、最小权限、隐私保护、可验证运行和长期可迁移性为基础的 AI Governance（人工智能治理）框架。Core 关注能够服务不同 System Owner（系统所有者）的公共能力，不绑定特定个人、设备、账号、路径或私人项目。

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

项目目前处于 XINGSHU 2.0 Phase 1（基础设施与公开边界建立阶段）。Public Governance v0.1 candidates（公共治理 v0.1 候选）已建立，当前状态为 `candidate`，尚未激活为正式 Public Core Governance（公共核心治理）。Schema、Adapter 与 Runtime 尚未作为公开实现发布。

## Security（安全）

报告安全问题前，请阅读 [SECURITY.md](SECURITY.md)。请勿在 Issue、Pull Request、Discussion 或 Commit 中提交任何 Secret（秘密值）或私人数据。

## License（许可证）

本项目采用 [Apache License 2.0](LICENSE)。
