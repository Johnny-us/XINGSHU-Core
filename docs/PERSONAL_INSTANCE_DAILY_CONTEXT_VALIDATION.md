---
type: non-normative-reference-validation-note
scope: public-status-only
status: reference
updated: 2026-10-01
validation_milestone: M3C-B2_Retry_PASS
production_ready: false
contract_effect: none
authorization_effect: none
---

# Personal Instance Daily Context Validation（私人实例日用上下文验证说明）

这是 Non-normative Reference Validation Note（非规范性参考验证说明）：不是 Public Core Contract（公共核心契约），不是私人实例模板，不是生产就绪声明。本文不包含私人数据，只描述一个有边界的验证里程碑。

## 1. Purpose（目的）

同步一个独立维护的私人 Personal Instance 已完成的真实本地验证，公开里程碑冻结为 `M3C-B2 Retry = PASS`。该实例复用现有 Public Core / P5 契约与精确条目读取能力，以自己的客户端桥和访问控制连接 Desktop Codex（桌面 AI 客户端）。本次不是新版本、产品发布或新的核心采用事件。

## 2. Boundary（范围）

验证限于一个获明确授权的真实精确条目、一个逻辑桌面客户端和一次最终上下文披露。显式授权限定用途、条目、内容版本、数量／字节上限与有效期；验证结束后权限被消费并撤销。

公共仓库自身的测试继续使用 Synthetic Fixtures（合成测试夹具），不包含真实知识正文、私人注册表、权限记录、路径、内容指纹或审计文件。私人验证不提供可从本仓库直接安装的整套日用上下文系统。

## 3. Generic validated flow（通用已验证流程）

```text
普通任务意图
→ 确定性的注册表元数据定位
→ 显式、有边界的一次性授权
→ 固定内容验证与 P5 精确条目解析
→ 当前桌面客户端恢复一次长期上下文
→ 消费授权并撤销
→ 后续新会话访问拒绝
```

该实例能从自然语言意图定位已登记上下文，用户无需手工填写来源路径或内部权限对象标识。定位成功不等于取得权限，仍须经过独立的显式授权步骤。此流程不是后台持续读取。

## 4. Persistent Registry + Ephemeral Access（持久注册表与临时访问）

这是 Personal Implementation Pattern（私人实现模式），不增加公共 Schema（结构合同）。

| 部分 | 已验证模式 | 权限含义 |
|---|---|---|
| Persistent Context Registry（持久上下文注册表） | 仅元数据、确定性路由、不存正文 | 不授予来源读取权，不是允许清单 |
| Ephemeral Access（临时访问） | 显式授权、精确条目、有限时效与数量／字节范围；本次配置为一次性 | 使用后消费和撤销，失效或后续访问默认拒绝 |

## 5. Safety properties observed（已观察到的安全行为）

- 注册表定位与正文读取分离，存在的来源不会自动取得读取许可。
- 授权绑定精确条目与固定内容版本；没有因为来源变化而自动扩大许可。
- 一次最终披露后消费授权并撤销；后续新会话访问拒绝。
- 旧接口不能绕过本次关闭状态取得真实正文。
- 验证不依赖全库扫描、递归链接展开、后台索引或永久许可。

这些结论针对已执行的受控验证，不构成对所有客户端、操作系统或调度情况的安全保证，也不提供恶意同用户进程隔离或通用身份认证保证。

## 6. Multi-instance handoff finding and repair（多实例交接发现与修复）

私人客户端桥的早期验收暴露了一个问题：额外 MCP 进程启动可能过早撤销尚未领取的一次性交接许可。私人实现修复并验证后，正常进程启动不会自行消费完整且尚未领取的交接许可；Single-use Claim（一次性领取）发生在 Resolve Admission（解析准入）处，并受 Cross-process Serialization（跨进程序列化）保护。

已完成多实例合成竞争验证和有多实例启动的真实重试验收；最终披露保持一次，使用后访问仍拒绝。这是私人实现的验证经验，不是新增公共核心规范、Schema 或随附并发实现。

## 7. What this does not prove（尚未证明或完成的能力）

`production_ready=false`。本里程碑不证明以下能力已经完成：

- ChatGPT Web shared-context path（网页端共享上下文路径）；
- Multi-Source runtime（多来源运行）；
- 跨设备验收、所有 AI 客户端支持或完整多客户端产品；
- 持续／后台运行、长期免确认访问、自动续期或全库授权；
- 自动个性化记忆、语义记忆、后台索引或完整对话提炼管线；
- OpenWiki 集成；
- P6、生产就绪或通用安装包。

## 8. Public Core vs Personal Instance separation（公共核心与私人实例分工）

| 层 | 本次说明的准确含义 |
|---|---|
| Public Core / P5 | 保留既有候选契约、精确条目运行入口与合成公共测试；默认关闭 |
| 独立私人实例 | 自己维护客户端桥、注册表路由与临时访问控制，并完成上述有边界真实验证 |
| 本文 | 公开状态说明，不分发私人实现或私人证据，不改变代码、合同、版本、授权或激活状态 |

Private Validation（私人验证）不等于 Public Core Bundled Product（公共核心随附产品）。公开文档、测试通过或仓库版本变化均不自动采用、激活或授权任何私人实例。

## 9. Next work（后续工作）

后续能力需按独立范围与验收推进；本里程碑不为未完成项授予实施或发布权限。公共说明应继续区分公共合同、私人实现、合成测试、真实有边界验收与生产能力。

相关公开说明：[README](../README.md)、[本地只读运行时](LOCAL_READ_ONLY_CONTEXT_RUNTIME.md)、[Obsidian 桥接](OBSIDIAN_CONTEXT_BRIDGE.md)。
