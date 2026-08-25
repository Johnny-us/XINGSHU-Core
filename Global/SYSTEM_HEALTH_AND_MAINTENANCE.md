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

# System Health & Maintenance（系统健康与维护）

> 本文件定义 XINGSHU Public Core（星枢公共核心）的通用健康与维护规则。它继承 [Global Governance（全局治理总纲）](00_GLOBAL_GOVERNANCE.md)，不保存任何 Personal Instance（私人实例）的设备、账号、路径、运行状态或维护历史。

## 1. Layered Health（健康状态必须分层）

不能因为某一层正常，就宣布整个系统健康。具体健康维度随真实架构调整，典型包括：

- Cloud Health（云端健康）：当前正式云端文件、治理结构与云服务；
- Local Health（本地健康）：已登记设备的本地文件、权限与运行环境；
- Sync Health（同步健康）：本地与正式云端是否一致，是否出现冲突或停滞；
- Knowledge Interface Health（知识界面 / 索引层健康）：当前实际使用的知识界面、索引与链接是否可用；
- Version Control Health（版本控制健康）：仅在已接入版本体系时检查仓库、分支和工作区；
- Agent Health（AI 代理健康）：已正式接入的 AI Agent 是否能读取正确治理并执行当前职责；
- Domain / Risk Health（领域 / 风险健康）：仅在已启用 Domain Pack（领域包）、Protected Action（受保护动作）或持续高影响自动化时检查领域规则版本、Intended Use（预期用途）、Professional Authority（专业决策资格 / 授权）、审批链、风险阈值、关键数据新鲜度、累计影响、Emergency Stop（紧急停止）与恢复条件是否仍有效；
- Context / Profile Health（上下文 / 画像健康）：当系统已持续使用 Role / Stage / Competence / Authority 等画像时，检查关键字段是否 `stale`、是否出现跨领域能力泄漏、重复提问、用户纠正未被吸收、任务级推断被错误提升为全局结论、敏感信息过度保存，或高风险授权依赖 `inferred` 的情况；
- Interaction Friction Health（交互摩擦健康）：检查系统是否出现“低风险任务先问卷”“连续低价值问题”“同一信息重复确认”，或为了显得个性化而增加无必要提问；若出现，应优先缩减提问，而不是要求用户维护更复杂设置；
- Adaptation Value Health（适配价值健康）：检查长期使用后，用户是否更少重复解释自己，是否减少无意义技术选择与术语暴露，结果是否更贴近当前角色 / 领域 / 能力水平，以及系统是否在用户能力变化后同步调整帮助方式；“记住更多内容”本身不等于适配价值提高；
- Configuration Drift Health（配置漂移健康）：当 XINGSHU 已对 AI Provider、版本控制、Environment（环境）、Workspace（工作区）或其他工具形成目标配置时，检查 `desired / observed / applied` 是否一致、Adapter 映射是否因平台更新失效、权限是否发生意外扩大 / 缩小，以及用户意图是否仍能被当前 Provider 正确实现；
- Recorder / Backup / Credential Health（日志汇聚 / 备份 / 凭据健康）：仅在对应组件已经真实建立并承担正式职责时纳入。

具体软件只是当前实现，不是永久健康架构。“云端可见”不等于“本地已同步”；“文档结构正常”也不等于设备、同步、自动化、日志或恢复能力都正常。

## 2. AI Maintenance Loop（AI 维护闭环）

技术维护默认采用：

`检查 → 发现异常 → 判断风险 → 低风险修复 → 验证 → 记录`

AI 应主动完成明确、低风险、可恢复、影响范围可控的技术修复，不把技术判断责任转交给普通用户或 System Owner（系统所有者）。若因离线、额度、权限、工具缺失或外部服务故障暂时无法闭环，应保存真实状态与恢复点，在能力恢复后继续。

## 3. Automatic Repair Boundary（自动修复边界）

允许主动处理的典型事项：

- 链接、索引、状态或日期等明显漂移；
- 原因明确且可恢复的配置小问题；
- 不改变核心治理架构的目录或记录一致性问题；
- 已有安全恢复路径的低风险技术维护。

必须先取得正确 Authorized Human（经授权的人类）明确批准的边界统一继承 Active Global Governance（当前有效全局治理），包括：

- Destructive Operations（破坏性操作）或明显不可逆、高恢复成本的数据 / 系统变更；
- Material Impact（重大现实影响），例如显著财务、法律、信誉、重要关系、重大时间承诺等现实后果；
- 重大隐私、安全或权限边界变化；
- 宪法级治理修订，或会放宽 / 绕过 Active Global Governance 的临时例外。

版本控制初始化、同步结构、Source of Truth（唯一正式来源）迁移等技术动作，不因名称本身自动升级为 System Owner 决策；AI 必须先评估其真实风险、可恢复性与现实影响，只有进入上述人类决策边界时才升级。

### 3.1 High-Risk Capability Drift & Circuit-Breaker Health（高风险能力漂移与熔断健康）

若系统已启用真实资金、患者相关临床支持、Production（生产环境）发布、客户最终交付 / 公开发布、批量商业动作或其他 Protected Action（受保护动作），健康检查不得只判断“服务是否在线”，还必须检查治理边界是否仍成立。至少包括：

- 当前模型、Agent、插件、工具、API、账号或外部平台能力是否发生会扩大执行范围的变化；
- Professional Authority（专业决策资格 / 授权）与审批责任人是否仍有效，是否出现身份、角色或权限漂移；
- 关键事实、市场数据、医学 / 专业规范、库存 / 价格、部署环境或其他时效性输入是否达到对应领域要求；
- 单次动作与累计动作是否仍位于授权金额、数量、频率、对象、时间、渠道和影响范围内；
- Emergency Stop / Circuit Breaker（紧急停止 / 熔断）是否真实可用，触发后是否能够阻止后续执行并保留证据；
- 是否出现重复失败、行为漂移、Prompt Injection（提示注入）、异常外部指令、凭据异常或其他应暂停执行的信号。

发现上述任一关键条件失效时，不得以“过去一直正常”或“AI 判断有把握”为理由继续 Protected Action。应优先暂停受影响能力、保存状态与证据、完成重新验证；只有恢复到可验证的安全边界后才能重新启用。

### 3.2 Context Calibration Health（上下文校准健康）

若系统使用渐进式画像进行长期个性化，维护检查至少关注：

- 同一字段的 `confirmed / inferred / unknown / stale` 是否与实际证据一致；
- 画像是否保留正确作用域，Task / Project 级推断是否被错误提升到 Domain / Global；
- 用户自然语言纠正是否能够及时覆盖低风险错误推断；
- 是否因为早期 Beginner / Expert 判断长期选择性忽略相反证据；
- 是否出现与当前任务无关的敏感属性推断 / 长期保存；
- 高风险执行是否有任何关键授权仅来自 `inferred`；
- 用户询问适配原因时，系统是否能说明“知道什么、猜什么、为什么这样处理”。

发现画像漂移或误判时，优先降级对应字段到更保守 Evidence State（证据状态）、缩小作用域或标记 `stale`；不得为了保持“系统一直很懂用户”的表象而保留错误画像。

### 3.3 Adaptation Value Health（适配价值健康）

XINGSHU 的长期成长不能只用 Memory（记忆）数量、画像字段数量、接入模型数量或自动化数量衡量。健康检查应关注这些积累是否真实降低用户为了获得正确帮助所承担的解释与技术负担，同时保持结果质量、安全和可纠正性。

可优先观察以下信号：

- Explanation Burden（解释负担）：同类任务中，用户是否仍需要反复解释已经确认且仍有效的身份、偏好、项目与工作方式；
- Technical Exposure Burden（技术暴露负担）：普通用户是否仍被频繁要求选择模型、Agent、插件、命令行或其他本应由系统编排的技术路径；
- Rework / Correction Load（返工 / 纠正负担）：因错误画像、错误上下文或不合适解释深度导致的大幅返工与纠正是否下降；
- Competence Adaptation（能力适配）：用户真实能力提高或下降后，系统是否能够调整解释、教学与自主执行深度，而不是永久停留在旧判断；
- Outcome Fit（结果符合度）：在适用 Domain Pack 已定义 Acceptance Criteria（验收标准）时，长期结果是否更稳定地满足用户当前目标与领域验收条件；
- Memory Discipline（记忆纪律）：是否通过提炼、过期、作用域和正式知识提升形成更清晰的长期结构，而不是无限堆积聊天和观察。

这些指标默认用于发现趋势，不应被机械优化成“问题越少越好”或“用户越少参与越好”。任何减少摩擦的优化仍必须服从安全、专业责任、用户学习目标、第三方权益与必要授权。

### 3.4 Configuration Drift Health（配置漂移健康）

当 XINGSHU 已经依据 [Architecture & Integration Principles（架构与集成原则）](ARCHITECTURE_AND_INTEGRATION_PRINCIPLES.md) 中的 Human Configuration Contract（人类配置契约），对外部 Provider、AI Agent、版本控制、Environment（环境）、Workspace（工作区）或其他工具形成配置目标时，维护检查不得只判断“是否连接成功”，还应检查配置语义是否仍然成立。

至少关注：

- `desired`：当前用户上下文与治理要求得到的目标状态；
- `observed`：当前平台 / 工具实际检测到的状态；
- `applied`：XINGSHU 最后一次成功实施并验证的状态；
- Provider Adapter（能力提供方适配器）的映射、版本与支持等级是否仍有效；
- 平台 UI、API、权限模型、默认值或产品命名变化后，旧配置是否仍代表同一用户意图；
- 是否出现权限意外扩大、确认边界消失、记忆 / 个性化失效、配置被平台重置或工具状态与 XINGSHU 记录不一致；
- 当前无法自动读取 / 写入的配置是否被错误标记为“已完成”。

发现配置漂移时，默认采用：

`检测差异 → 判断风险 → 保留用户上层意图 → 更新 / 重新验收 Adapter → 自动修复或生成辅助步骤 → 验证 observed 状态 → 记录`

低风险、可恢复且不会扩大权限的配置漂移可以主动修复；涉及重大权限、隐私、Protected Action、Material Impact 或宪法级边界变化时，按 Active Global Governance 升级处理。

不得通过修改 Human Configuration Contract 来掩盖 Provider 无法实现的问题。若当前平台只能 `assisted / recommended / unsupported`，应诚实保留该状态，并向用户提供人类可理解的结论。

## 4. Verification Requirements（验证要求）

修复完成不等于任务完成。AI 必须重新检查实际状态，并用使用者可理解的语言向 System Owner 或当前请求者说明：

- 发现了什么问题；
- 执行了什么修复；
- 修复后是否验证通过；
- 是否仍存在未解决风险或外部阻碍。

## 5. Current Status（当前状态）

本文件当前为 Public Core v0.1 `candidate`。它定义通用健康与维护规则，但不包含任何实例设备、账号、路径或运行状态；在完成审查、批准与发布流程前，不具有正式 Public Core 治理效力。
