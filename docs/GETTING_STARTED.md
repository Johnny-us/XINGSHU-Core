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

# Getting Started（开始使用）

本指南说明如何从 XINGSHU-Core（星枢公共核心）建立一个物理隔离的 Personal Instance（私人实例）。Public Core 提供通用规则、架构、治理、模板和使用说明；它不承载任何用户的私人配置或运行数据。

当前 Public Governance v0.1 仍为 `candidate`。候选内容可以用于审查和试验，但在完成正式治理发布前，不应被描述为已经激活的公共治理版本。

## 1. Understand the Three Roles（理解三类职责）

- **Core（公共核心）**：公共规则、架构、治理、模板和公开说明的 Source of Truth（唯一正式来源）；
- **Personal Instance（私人实例）**：实例身份、授权、配置、项目、偏好和运行状态的 Source of Truth；
- **Backup（备份）**：只用于恢复、审计和历史追溯，不是活动工作区。

详细定义参见 [Core / Personal Instance / Backup Boundary（核心、私人实例与备份边界）](../CORE_PERSONAL_BOUNDARY.md) 和 [Personal Instance Model（私人实例模型）](PERSONAL_INSTANCE_MODEL.md)。

## 2. Obtain Public Core（取得公共核心）

从正式 Public Core Repository（公共核心仓库）取得需要审查的内容。不要直接在 Public Core 工作区中建立个人配置、保存工作记录或运行私人项目。

## 3. Select a Core Version（选择 Core 版本）

开始采用前确认：

- 来源是正式公共仓库；
- Commit、Tag 或 Release（发布版本）明确；
- 治理状态是 `candidate`、`active` 还是 `deprecated`；
- 安全、许可证、变更和版本说明可读取；
- 选择范围中没有混入私人文件。

当前 Public Governance v0.1 是 `candidate`，只能作为审查或试验候选，不应被标记为已经激活的公共治理版本。

## 4. Establish an Adopted Core Baseline（建立已采用核心基线）

Explicitly Adopted Core Baseline（明确采用的核心基线）是 Personal Instance 将要采用的、可追溯且范围明确的公共版本集合。建立基线至少应记录：

- 选定的版本、Commit 或 Release；
- 对应治理状态；
- 实际采用的文件范围；
- 差异、兼容性、隐私和授权检查结果；
- 后续验证与回滚依据。

基线必须通过单向、显式采用建立。可以使用经过审查的版本快照或稳定版本引用，但不得通过以下方式实现：

- 自动双向同步；
- 目录镜像；
- 符号链接；
- Core 更新自动覆盖 Personal Instance；
- 把 Personal Instance 放入 Public Core 的版本控制范围。

版本较新、文件已经复制或 Public Core 已发布，都不代表实例已经采用。只有完成差异检查、明确采用和验证后，才形成该实例的 Adopted Core Baseline。

## 5. Create a Separate Personal Instance（创建独立私人实例）

在 Public Core 工作区之外创建一个独立、非公开的 Personal Instance。两者必须保持物理隔离，不共用同一个 Git Repository（Git 仓库），也不建立镜像、符号链接或自动同步。

私人实例的存储、访问控制和 Backup 方式应根据用户自己的风险、隐私和恢复要求配置，不写入 Public Core。

## 6. Use Templates & Configure the Personal Overlay（使用模板并配置私人覆盖层）

采用单向、显式复制：

1. 将 [`templates/XINGSHU_ROOT.template.md`](../templates/XINGSHU_ROOT.template.md) 复制到 Personal Instance，并重命名为 `XINGSHU_ROOT.md`；
2. 将 [`templates/AGENTS.template.md`](../templates/AGENTS.template.md) 复制到 Personal Instance，并重命名为 `AGENTS.md`；
3. 在 Personal Instance 中记录 Adopted Core Baseline；
4. 在 Personal Overlay（私人覆盖层）中配置实例治理主体、授权、偏好、环境、项目和运行状态；
5. 不修改 Public Core 模板来保存个人信息，也不建立两个目录之间的自动更新关系。

Personal Overlay 可以在 Adopted Core Baseline 之上增加实例事实或更严格规则，但不得静默削弱 Core 的安全、隐私、授权和风险边界。

模板复制只建立候选结构，不代表实例已经激活，也不授予 Agent 任何权限。

## 7. Activate the Agent Entry（激活代理入口）

只有同时满足以下条件，Personal Instance 才能按自身治理激活 Agent Entry（代理入口）：

- `XINGSHU_ROOT.md` 已确认当前实例根身份；
- Adopted Core Baseline 的版本、范围和状态可追溯；
- Personal Overlay 已在私人环境中完成必要配置；
- Agent 已完成与任务风险匹配的接入验收；
- 最小权限、授权边界、暂停和撤销路径明确；
- Core / Personal / Backup 物理边界验证通过；
- 没有 Secret 或私人数据回流 Public Core。

激活只对当前 Personal Instance 生效，不会修改 Public Core，也不会授权其他实例或 Agent。

## 8. Validate the Boundary（验证边界）

开始使用前确认：

- Public Core 中没有个人身份、设备、账号、项目、工作记录或私人配置；
- Personal Instance 不在 Public Core 的版本控制范围内；
- 两个目录之间不存在符号链接、镜像或自动双向同步；
- Secret 只保存在适合实际架构的受保护凭据系统中；
- Backup 与活动实例分离，并具有可验证的恢复用途；
- Agent 只能获得当前职责需要的最小权限；
- 候选治理没有被误报为 `active`。

## 9. Contribute Back Safely（安全贡献公共候选）

Personal Instance 中形成的通用经验不能直接复制回 Public Core。贡献前必须完成：

`通用价值判断 → 抽象 → 去实例化 → 去身份化 → 去设备化 → 去账号化 → 去路径化 → Secret 扫描 → 来源与许可证检查 → Public Review`

只有独立、可公开、可维护且不依赖私人运行状态的内容，才能成为 Public Core Candidate（公共核心候选）。
