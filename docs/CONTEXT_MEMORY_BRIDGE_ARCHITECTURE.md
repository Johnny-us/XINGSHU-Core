# XINGSHU Context & Memory Bridge Architecture（星枢上下文与记忆桥接架构）

> Status: `design-proposal`
>
> Governance effect: `none`
>
> Runtime effect: `none`
>
> Implementation status: `not-implemented`
>
> 本文定义 XINGSHU 的长期桥接方向，不激活任何新能力，不改变任何 Personal Instance，也不宣称任何具体 AI 产品已经获得完整兼容。

## 1. Core Identity（核心定位）

XINGSHU 不是 Knowledge Base（知识库）、Project Management Database（项目管理数据库）或 Data Lake（数据湖）。

XINGSHU 的核心职责是：

> **作为用户控制的 AI Context, Memory, Habit & Governance Layer（上下文、记忆、习惯与治理层），在用户自己的信息源与不同 AI 客户端之间进行受控桥接。**

因此，XINGSHU 应保持一个 `thin core`（薄核心）：

- 长期保存真正属于用户跨 AI、跨项目、跨时间使用的稳定记忆与习惯；
- 保存权限、治理、来源、路由和调用规则；
- 对项目、文档、知识库和业务状态只保存最小引用与访问策略；
- 原始资料和项目状态继续由它们各自的 Source of Truth（事实源）维护；
- AI 需要上下文时，由 XINGSHU 按需解析、检索、验证并提供最小必要信息。

一句话：

> **星枢不替用户重新存一遍数字世界；星枢负责记住用户、找到正确来源，并把正确的上下文交给正确的 AI。**

## 2. Three-Layer Model（三层模型）

```text
┌─────────────────────────────────────────────┐
│ External Sources of Truth                   │
│ 外部事实源                                   │
│                                             │
│ Obsidian / Google Drive / Git / Local Files │
│ Notion / Databases / Project Systems / ...  │
└──────────────────────┬──────────────────────┘
                       │
                 Source Adapters
                       │
                       ▼
┌─────────────────────────────────────────────┐
│ XINGSHU Thin Core                           │
│ 星枢薄核心                                   │
│                                             │
│ Identity / Memory / Habits / Preferences    │
│ Governance / Permissions / Routing          │
│ Context References / Provenance             │
│ Retrieval / Validation / Audit              │
└──────────────────────┬──────────────────────┘
                       │
              Client Adapters / Gateways
                       │
                       ▼
┌─────────────────────────────────────────────┐
│ Compatible AI Clients                       │
│ Codex / ChatGPT / WorkBuddy / other agents  │
└─────────────────────────────────────────────┘
```

该模型同时追求：

- `source-neutral`：不绑定某一种知识或项目软件；
- `provider-neutral`：不绑定某一家 AI；
- `source-of-truth-preserving`：不制造多份互相竞争的正式事实；
- `user-controlled`：用户决定什么可被读取、记忆、引用和提供给 AI。

## 3. What XINGSHU Owns（星枢真正应该保存什么）

XINGSHU 可以原生管理以下类型的稳定状态。

### 3.1 Identity（身份与长期环境）

例如：

- 用户偏好的语言；
- 用户长期使用的设备角色；
- 已确认的工作环境约束；
- AI Agent / Device 身份绑定；
- 与长期调用相关的稳定环境事实。

### 3.2 Memory（长期记忆）

例如：

- 已明确确认的长期偏好；
- 经治理晋升的长期事实；
- 跨会话仍然有价值的约束；
- 有来源、有效期和复审条件的长期记忆。

### 3.3 Habits & Preferences（习惯与偏好）

例如：

- 低风险、可恢复步骤不希望反复确认；
- 中文优先；
- 某类任务的固定表达或交付方式；
- 某类工具的使用偏好。

### 3.4 Governance & Policy（治理与策略）

例如：

- 哪些信息允许哪些 AI 查看；
- 哪些来源禁止外部 AI 访问；
- 哪些信息失效；
- 哪些记忆存在冲突；
- 写入、晋升、删除和审计规则。

### 3.5 Context Routing（上下文路由）

例如：

- 当用户提到某个项目名称时，应到哪里查；
- 当用户说“之前我们定过”时，应优先检查哪些记忆；
- 当前问题属于哪个 scope；
- 哪个 Source Adapter 可以读取对应来源。

这些是 XINGSHU 的原生职责。

## 4. What XINGSHU Does Not Own（星枢不应该保存什么）

以下内容默认不应复制进入 XINGSHU 作为正式数据本体：

- 完整项目文件；
- 项目全部历史记录；
- 完整 Obsidian Vault；
- Google Drive 文档副本；
- Git 仓库代码；
- 大量聊天记录原文；
- 任务管理系统中的完整任务表；
- 照片、视频和大附件；
- 任何已经由其他系统可靠维护的业务状态本体。

原则：

> **Do not duplicate a reliable Source of Truth without a demonstrated need.**
>
> 已经存在可靠事实源时，不为了“接入 AI”而复制第二份正式事实。

## 5. Project State Boundary（项目状态边界）

Project State（项目状态）尤其容易让 XINGSHU 变重并产生过期副本。

因此：

```text
Wrong / 不推荐

XINGSHU
├── Shadowrocket 完整项目
├── XINGSHU-Core 完整进度历史
├── 所有项目任务
└── 所有完成事项
```

推荐：

```text
External Source of Truth
Obsidian / Git / project files
├── 项目完整状态
├── 决策记录
├── 完成事项
└── 当前进度

          ▲
          │ resolve on demand
          │ 按需解析
          │
XINGSHU
└── Context Reference
    ├── project identity
    ├── source locator
    ├── access scope
    ├── provenance policy
    ├── freshness policy
    └── retrieval rule
```

XINGSHU 可以知道“有这个项目、应该去哪里找、谁可以看”，但不应该默认维护第二套完整项目状态。

### 5.1 Example（示例）

用户问：

> “Shadowrocket 冷启动问题最后怎么判断的？”

推荐流程：

```text
AI
↓
XINGSHU detects project/context cue
↓
resolve Context Reference
↓
read current authorized source in Obsidian / project files
↓
validate provenance + freshness
↓
return minimum necessary context
```

而不是：

```text
AI
↓
read a duplicated and possibly stale project copy stored inside XINGSHU
```

## 6. Context Reference（上下文引用）

对于外部项目和知识源，XINGSHU 应优先保存 Lightweight Context Reference（轻量上下文引用），而不是内容本体。

候选最小字段：

```text
reference_id
context_type
canonical_name
source_id
source_locator
access_scope
provenance_policy
freshness_policy
last_verified_at
retrieval_hint
```

可选字段：

```text
content_fingerprint
human_label
related_memory_ids
```

不应默认保存：

```text
full_project_content
full_document_copy
full_history
large_attachments
```

Context Reference 的目标是：

> **证明“这个上下文存在、在哪里、如何安全获取”，而不是复制这个上下文本身。**

## 7. Native Memory vs External Event（原生记忆与外部事件）

必须区分：

### Event / Project Fact（事件 / 项目事实）

例如：

> “某项目今天完成 B3。”

这通常属于项目记录，应保留在项目事实源。

### Durable Memory / Habit（长期记忆 / 习惯）

例如：

> “用户不希望低风险步骤被反复询问确认。”

这属于跨项目、跨 AI、长期有效的行为偏好，适合由 XINGSHU 管理。

### Context Anchor（上下文锚点）

例如：

> “用户目前存在一个名为 XINGSHU-Core 的项目，其正式状态应从指定项目源解析。”

这可以由 XINGSHU 以轻量引用形式保存。

因此：

```text
项目事件 ≠ 长期记忆
项目完整状态 ≠ XINGSHU 原生状态
项目存在及其入口 = 可成为 Context Reference
跨项目稳定偏好 = 可成为 XINGSHU Memory / Habit
```

## 8. Source Adapter Contract（来源适配器契约）

每一种外部来源由 Source Adapter 负责安全读取。

```text
Obsidian Vault ──► Filesystem / Obsidian Adapter
Google Drive  ──► Google Drive Adapter
Git           ──► Git Adapter
Notion        ──► Notion Adapter
Local Folder  ──► Filesystem Adapter
Database      ──► Database Adapter
```

最小只读能力：

```text
discover(scope)
stat(item)
read(item)
list(scope)
```

可选：

```text
search(query)
watch(scope)
```

未来写入能力必须独立授权：

```text
write(item)   # default disabled
```

Source Adapter 必须保留 Provenance（溯源）并尊重来源本身的 Source of Truth 地位。

## 9. Retrieval Without Ownership（检索不等于占有）

XINGSHU 可以建立索引，但索引不是新的事实源。

推荐层级：

```text
External Source of Truth
        ↓
Metadata / lightweight index
        ↓
Optional local full-text index
        ↓
Optional semantic index
        ↓
XINGSHU retrieval
```

任何缓存、索引或派生数据都必须满足：

- 可删除；
- 可重建；
- 不与原始来源竞争 Source of Truth；
- 有明确 retention（保留）策略；
- 不自动晋升为 Memory；
- 不因缓存存在而绕过原始来源的新鲜度检查。

原则：

> **Index is disposable; provenance is not.**
>
> 索引可以重建，来源关系不能丢失。

## 10. XINGSHU Runtime Responsibilities（Runtime 职责）

当 AI 请求个人上下文时：

```text
AI Request
   ↓
Client Adapter
   ↓
Intent / Context Cue Detection
   ↓
Memory / Habit lookup
   ↓
Context Reference resolution (when needed)
   ↓
Permission / Scope check
   ↓
Source retrieval
   ↓
Freshness / Provenance validation
   ↓
Minimum Necessary Context
   ↓
AI Client
```

Runtime 至少负责：

- Identity；
- Memory / Habit lookup；
- Context routing；
- Permission / Scope；
- Retrieval orchestration；
- Provenance；
- Freshness validation；
- Conflict handling；
- Audit；
- Minimum disclosure。

## 11. AI Client Side（AI 客户端侧）

XINGSHU 不应为每一家 AI 重写完整逻辑。

通过 Client Adapter / Protocol Gateway 暴露稳定语义。

第一版候选只读能力：

```text
xingshu.status()
xingshu.recall(query, scope?)
xingshu.resolve_context(query, scope?)
xingshu.get_reference(reference_id)
```

其中：

- `recall`：优先处理 XINGSHU 原生长期记忆、偏好与习惯；
- `resolve_context`：需要项目或外部知识时，解析引用并从事实源读取；
- `get_reference`：返回来源和可验证定位，不等同于项目数据库读取。

不建议把 `xingshu.get_project()` 设计成 XINGSHU 自己维护完整项目状态的接口。

## 12. MCP Position（MCP 的位置）

MCP 可以作为优先的 AI 侧开放协议，但不是 XINGSHU 本体，也不是唯一协议。

```text
XINGSHU Runtime
      │
 ┌────┼───────────┐
 ▼    ▼           ▼
MCP  Tool API   CLI / other adapters
```

核心契约必须保持协议中立，使不支持 MCP 但具有可靠 Tool API / Plugin / App / CLI 能力的客户端仍可以通过 Adapter 接入。

## 13. Skill Position（Skill 的位置）

Skill 负责告诉 AI “什么时候、为什么、如何调用 XINGSHU”。

例如：

- 用户说“我以前说过……”时优先 `recall`；
- 用户询问某个项目最新状态时使用 `resolve_context`，不要把旧聊天记忆当事实；
- 来源冲突时返回冲突而不是猜测；
- 不得把一次项目事件自动写成长期记忆。

因此：

```text
Skill = behavior / workflow instruction
Protocol = transport
XINGSHU Runtime = memory + habit + context governance
External Sources = project / knowledge / document facts
```

## 14. Obsidian as First External Source（Obsidian 作为首个外部事实源）

Obsidian 是第一个实验对象，不是 XINGSHU 的组成前提。

推荐第一阶段：

```text
Obsidian Vault
      │
      │ explicit allowlist + read only
      ▼
Filesystem Source Adapter
      │
      ▼
XINGSHU Context Resolver
```

必须：

- 显式指定允许范围；
- 只读；
- 默认排除 `.obsidian`；
- 防止 path traversal；
- 防止 symlink escape；
- 不修改原文件；
- XINGSHU 的索引、缓存、日志不得写入 Vault；
- 项目状态继续以原始笔记 / 项目记录为准。

未来 Obsidian Plugin 主要解决 UX，而不是改变 Source of Truth。

## 15. Compatibility Definition（兼容性定义）

“任意知识源 → XINGSHU → 任意 AI”不是无条件承诺。

准确含义：

- 能够被文件、API、数据库、导出接口或其他受控方式访问的来源，可以开发 Source Adapter；
- 能够使用 MCP、Tool API、Plugin/App、CLI 或其他扩展机制的 AI，可以开发 Client Adapter；
- 完全封闭的软件可能无法直接接入。

兼容性由 Capability（能力）决定，而不是由品牌名称决定。

## 16. Security & Privacy Invariants（安全与隐私不变量）

1. `read-only-first`：来源接入第一阶段默认只读；
2. `fail-closed`：权限、来源或范围不明确时拒绝；
3. `least-privilege`：Adapter 只获得最低权限；
4. `least-disclosure`：AI 只获得当前任务必要上下文；
5. `provenance-first`：外部事实必须可追溯；
6. `source-of-truth-preserving`：不无理由制造正式副本；
7. `no-automatic-memory-promotion`：外部命中不自动成为长期记忆；
8. `freshness-aware`：项目状态类信息必须考虑来源新鲜度；
9. `auditable`：重要访问和未来写入应可审计；
10. `portable`：替换知识源或 AI 不应迫使用户重建全部记忆治理。

## 17. Recommended Pilot Sequence（推荐实验顺序）

| Phase | 目标 | Public capability claim |
|---|---|---|
| B0 | Private Bridge Lab | No |
| B1 | Context Reference + Source Adapter contract | No |
| B2 | Obsidian / filesystem strict read-only adapter | No |
| B3 | 轻量索引 / 可重建全文检索 | No |
| B4 | `recall` / `resolve_context` Runtime contract | No |
| B5 | Read-only MCP Gateway | No |
| B6 | Codex 真实问题验证 | No |
| B7 | 第二 AI Client 验证 | No |
| B8 | Skill / workflow prototype | No |
| B9 | 连续使用，检查过期、冲突、误召回 | No |
| B10 | 第二 External Source 验证 | No |
| B11 | 脱敏、抽象、独立复审 | No |
| B12 | 再决定是否形成后续 Public Candidate | After review only |

## 18. Minimum Meaningful Success（最小有意义成功）

第一阶段成功不是“把 Obsidian 全部导入 XINGSHU”。

而是：

```text
User asks a project/history question
       ↓
XINGSHU remembers how to resolve it
       ↓
reads the current authorized source
       ↓
returns a provenance-backed answer
       ↓
stores no unnecessary duplicate project state
```

必须能够证明：

- XINGSHU 自身只保存必要的 Memory / Habit / Context Reference；
- 项目本体继续存在原事实源；
- 来源更新后，不需要人工同步一份“星枢项目副本”；
- AI 得到的是当前、可验证、最小必要的上下文；
- 撤销来源权限后，AI 无法继续通过 XINGSHU读取该来源。

## 19. Non-Goals（当前非目标）

- 把 XINGSHU 做成第二个 Obsidian；
- 把所有项目资料迁入 XINGSHU；
- 把每一次项目进展都变成 Memory；
- 把所有外部资料永久缓存；
- 为每家 AI 复制一份个人资料；
- 用 Skill 替代 Runtime；
- 用 MCP 定义 XINGSHU 核心；
- 宣称所有知识库和所有 AI 已兼容。

## 20. Long-Term Product Shape（长期产品形态）

普通用户最终看到的可以非常简单：

```text
My memory & habits
● XINGSHU active

External context sources
● Obsidian connected (read only)
○ Google Drive
○ Other sources

AI clients
● Codex
○ ChatGPT
○ WorkBuddy
○ Other compatible clients
```

用户不需要把知识“搬进星枢”。

真正稳定的核心是：

```text
Memory / Habits / Governance
          +
Lightweight Context References
          ↓
      XINGSHU Runtime
       ↙          ↘
External Sources   AI Clients
```

这使 XINGSHU 保持轻量，同时继续承担其最初职责：让用户自己的记忆、习惯和上下文不再被锁在某一个 AI 产品中。