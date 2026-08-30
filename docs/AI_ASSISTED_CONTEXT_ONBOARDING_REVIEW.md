# AI-Assisted Context Onboarding Review（AI 辅助上下文接入复核）

> Status: `design-proposal`
>
> Governance effect: `none`
>
> Runtime effect: `none`
>
> Implementation status: `not-implemented`

## 1. Purpose（目的）

XINGSHU 不应尝试自行具备与用户 Primary AI（主使用 AI）相同的通用理解能力。

当用户已经在 Codex、ChatGPT、WorkBuddy 或其他兼容 AI 中工作，并希望把一个现有项目接入 XINGSHU 时，应允许该 AI 先理解项目、复核来源并生成 Context Reference（上下文引用）接入提案，再由 XINGSHU 执行确定性的安全校验与登记。

核心原则：

> **Use the Primary AI for semantic understanding; use XINGSHU for deterministic governance and enforcement.**
>
> 复杂语义理解交给主 AI；确定性的治理、边界和执行交给星枢。

## 2. Roles（角色分工）

### 2.1 Primary AI / Host AI（主 AI / 宿主 AI）

负责它擅长的语义工作，例如：

- 理解一个已有项目大致是做什么的；
- 识别项目根目录、README、索引页、决策记录等候选入口；
- 判断哪些内容更像当前 Source of Truth；
- 识别项目名称、别名和上下文线索；
- 建议合理的 retrieval hint（检索提示）；
- 发现明显重复、过期或互相冲突的候选来源；
- 向用户用自然语言解释“接入后星枢会知道什么”。

Primary AI 输出的是 **proposal（提案）**，不是最终授权事实。

### 2.2 XINGSHU（星枢）

负责它必须可靠完成的确定性工作，例如：

- Source Adapter 是否存在且可用；
- source locator 是否位于已授权 scope；
- 路径穿越、symlink escape、越权访问等安全检查；
- Reference Schema / Contract 验证；
- Context Reference 是否重名、重复或冲突；
- allowed clients / permissions 是否符合治理；
- provenance / freshness policy 是否完整；
- 是否满足 least privilege（最小权限）；
- 最终登记、暂停、撤销和审计。

XINGSHU 不应因为 Primary AI “认为安全”就跳过上述检查。

### 2.3 User / System Owner（用户 / 系统所有者）

用户拥有最终授权权。

第一版原则：

> **AI may propose; XINGSHU may validate; only authorized user intent may register.**

用户可以：

- 接受；
- 修改 scope；
- 限制允许的 AI；
- 改名；
- 拒绝；
- 稍后撤销。

对于用户已经明确发出“把这个项目接入星枢”的操作指令，产品可以把这视为明确授权意图的一部分，避免重复无意义确认；但任何扩大来源范围、增加高敏感权限或开启写入能力的变化仍需要独立授权。

## 3. Recommended Flow（推荐流程）

```text
User in Primary AI
“把这个项目接入星枢”
        ↓
Primary AI understands current project
        ↓
Primary AI prepares Context Registration Proposal
        ↓
XINGSHU validates proposal deterministically
        ↓
Policy / permission / source checks
        ↓
User-visible authorization decision
        ↓
XINGSHU registers lightweight Context Reference
        ↓
Future compatible AIs resolve current source on demand
```

重点：项目本体不因此迁移到 XINGSHU。

## 4. Context Registration Proposal（上下文登记提案）

Primary AI 可以生成候选提案，例如：

```text
proposal_type: context_reference
canonical_name: Project-A
context_type: project
source_type: obsidian
source_locator: Projects/Project-A/
source_of_truth_hint: README.md + project status note
retrieval_hint: use project overview first; inspect decision log when historical decisions are requested
requested_access_scope: read-only
requested_clients: current-client
freshness_policy: resolve_on_query
confidence: high
review_notes: project root and current-status note were found in the authorized source scope
```

这些字段只是候选输入。

XINGSHU 必须自行验证可验证字段，不得把 AI confidence 当作安全凭据。

## 5. Two Different Reviews（两种复核不能混淆）

### Semantic Review（语义复核）

由 Primary AI 擅长：

- 这是哪个项目？
- 哪个文件最像项目说明？
- 用户以后会用什么名字提到它？
- 哪些文档最可能回答项目状态问题？

### Governance Validation（治理校验）

由 XINGSHU 负责：

- 这个路径允许访问吗？
- 这个 AI 有权限吗？
- Reference 是否符合 Schema？
- 是否暴露了超出当前问题需要的范围？
- 来源是否还能验证？
- 是否产生重复或冲突引用？

因此：

```text
AI intelligence != authorization authority
AI 智能能力 ≠ 授权权力
```

## 6. Primary AI Is Replaceable（主 AI 必须可替换）

虽然第一阶段可以用 Codex 做 Pilot，但 XINGSHU 不应把“主 AI”硬编码为 Codex。

```text
Today:   Codex -> XINGSHU
Later:   ChatGPT -> XINGSHU
Or:      WorkBuddy -> XINGSHU
```

只要客户端支持所需的 XINGSHU Client Adapter / Tool Contract，就可以承担 Primary AI Review 角色。

因此，XINGSHU 接受的是稳定的 `Context Registration Proposal` contract，而不是某一家模型的私有输出格式。

## 7. Candidate Interface Semantics（候选接口语义）

未来可以提供类似以下稳定能力：

```text
xingshu.inspect_source(scope)
xingshu.propose_context_reference(proposal)
xingshu.validate_context_reference(proposal_id)
xingshu.register_context_reference(proposal_id, authorization)
xingshu.revoke_context_reference(reference_id)
```

职责必须分开：

- `inspect_source`：只读查看已授权来源能力；
- `propose`：接受主 AI 的候选语义；
- `validate`：确定性检查，不产生正式挂载；
- `register`：在满足授权条件后，写入 XINGSHU 自己的轻量 Reference；
- `revoke`：终止星枢介导的后续访问。

第一版项目来源仍保持 read-only。`register` 只允许写 XINGSHU 自身的 Reference Registry，不允许写回用户项目。

## 8. Example（示例）

用户正在 Codex 中打开一个已有项目，并说：

> “把这个项目接入星枢，以后其他 AI 也能知道我说的是哪个项目。”

Codex 可以：

1. 阅读当前项目已有文件；
2. 判断项目名称和项目根；
3. 找到 README / status / decision log 等入口；
4. 生成 Context Registration Proposal；
5. 调用 XINGSHU 验证接口。

XINGSHU 再检查：

```text
source authorized?          PASS
read-only scope?            PASS
locator inside scope?       PASS
schema valid?               PASS
reference conflict?         NONE
client permission?          PASS
provenance policy present?  PASS
```

然后才允许形成：

```text
Context Reference: Project-A
Source of Truth: external project
Access: read-only
Freshness: resolve_on_query
```

此后 ChatGPT、WorkBuddy 或其他兼容客户端都可以通过同一个稳定项目身份请求 XINGSHU，而不需要重新理解项目的存储结构。

## 9. Failure Behavior（失败行为）

如果 Primary AI 判断错误：

- XINGSHU 的结构、安全和权限验证仍应阻止可验证的错误；
- 语义上无法确定的项目身份应标记为 ambiguous，而不是自动登记；
- 不允许通过“AI 高置信度”绕过用户授权；
- 不允许 AI 自动扩大 authorized scope 来完成接入。

如果 Source 后续移动或失效：

- Reference 标记为 `stale_locator` / `source_unavailable`；
- Primary AI 可以协助重新定位；
- XINGSHU 重新验证后再更新 Reference。

## 10. Why This Fits XINGSHU（为什么符合星枢定位）

XINGSHU 的竞争力不应建立在“比主 AI 更聪明”上。

它应建立在：

- 用户可控制；
- 跨 AI 稳定；
- 来源可追溯；
- 权限一致；
- 记忆与项目事实边界清晰；
- 接口可复用；
- 主 AI 可以替换但 Context Identity 不需要重建。

因此最合理的关系是：

```text
Primary AI = intelligence / interpretation
XINGSHU   = memory / context routing / governance / enforcement
Source    = authoritative project or knowledge data
User      = authority
```

## 11. Minimum Validation Criteria（最小验证标准）

该机制只有满足以下条件，才算完成最小闭环：

1. Codex（首个 Pilot）能对已有项目生成可用 Proposal；
2. XINGSHU 能独立拒绝越权或不合法 Proposal；
3. 用户无需迁移项目即可建立 Reference；
4. 登记操作只写 XINGSHU Reference，不写原项目；
5. 第二个兼容 AI 能通过同一个 Reference 获取项目当前上下文；
6. 更换 Primary AI 不要求重建已有 Context References。

## Related

- [Existing Context Onboarding](EXISTING_CONTEXT_ONBOARDING.md)
- [XINGSHU Context & Memory Bridge Architecture](CONTEXT_MEMORY_BRIDGE_ARCHITECTURE.md)
