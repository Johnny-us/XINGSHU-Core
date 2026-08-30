# Existing Context Onboarding（既有上下文接入）

> Status: `design-proposal`
>
> Governance effect: `none`
>
> Runtime effect: `none`
>
> Implementation status: `not-implemented`

## 1. Purpose（目的）

XINGSHU 不应要求新用户先把已有项目、知识库或工作资料迁移到 XINGSHU，才能开始使用。

很多用户在接触 XINGSHU 之前，已经拥有成熟的信息结构，例如：

- Obsidian Vault；
- Google Drive / OneDrive 等云盘；
- Git / GitHub 项目；
- Notion；
- 本地文件夹；
- 项目管理系统；
- 数据库或其他知识系统。

XINGSHU 应提供 Existing Context Onboarding（既有上下文接入）能力：

> **保留现有系统为 Source of Truth，只为需要跨 AI 调用的对象建立轻量 Context Reference。**

这不是 Migration（迁移），也不是 Import All（全部导入）。

## 2. Core Principle（核心原则）

```text
Existing project / knowledge source
        ↓
keep original Source of Truth
        ↓
XINGSHU creates Context Reference
        ↓
compatible AI resolves current context on demand
```

XINGSHU 保存“如何找到、如何授权、如何验证”，而不是默认保存项目本体。

## 3. Recommended New-User Flow（推荐新用户流程）

### Step 1 — Connect Source（连接来源）

用户选择已有来源，例如：

```text
☑ Obsidian
□ Google Drive
□ GitHub / Git
□ Notion
□ Local Folder
```

每个来源必须使用显式授权范围，默认只读。

### Step 2 — Discover Context Candidates（发现上下文候选）

Source Adapter 在已授权范围内发现可能有长期调用价值的对象，例如：

- project root；
- project index；
- project overview；
- stable knowledge collection；
- decision log；
- documentation root；
- other user-recognizable context anchors。

发现不等于注册。

XINGSHU 不应因为扫描到一个文件夹就自动把它变成长期记忆。

### Step 3 — Propose References（提出引用候选）

XINGSHU 向用户展示候选：

```text
发现 4 个可能的项目上下文：

[ ] XINGSHU-Core
    来源：Obsidian / Projects/XINGSHU-Core/

[ ] Shadowrocket
    来源：Obsidian / Projects/Shadowrocket/

[ ] Photography Archive
    来源：Drive / Photography/

[ ] Website Redesign
    来源：Git / website-redesign
```

用户可以：

- 注册；
- 忽略；
- 限制访问范围；
- 指定允许的 AI；
- 指定是否允许自动刷新元数据。

### Step 4 — Register Context Reference（登记上下文引用）

确认后，XINGSHU 仅保存轻量 Reference。

候选字段：

```text
reference_id
context_type
canonical_name
source_id
source_locator
access_scope
allowed_clients
freshness_policy
provenance_policy
retrieval_hint
last_verified_at
status
```

默认不保存：

```text
full_project_content
full_document_copy
full_history
large_attachments
```

### Step 5 — Resolve On Demand（按需解析）

以后用户可以在任何兼容 AI 中直接提到项目：

> “Shadowrocket 那个项目现在推进到哪里了？”

推荐流程：

```text
AI
↓
XINGSHU identifies context cue
↓
Context Reference lookup
↓
permission / scope check
↓
read current Source of Truth
↓
freshness + provenance validation
↓
minimum necessary context
↓
AI answer
```

不依赖用户重新上传整个项目，也不依赖 XINGSHU 内部保存旧项目副本。

## 4. Attach, Do Not Migrate（挂载，而不是迁移）

用户体验层可以使用“接入 / 挂载 / 关联”这类概念，而不应默认使用“导入全部资料”。

推荐语义：

```text
Attach project context
挂载项目上下文
```

而不是：

```text
Import project into XINGSHU
把项目导入星枢
```

这是为了保持：

- Source of Truth 唯一；
- XINGSHU Thin Core；
- 数据可迁移；
- 可撤销；
- 避免重复数据和过期副本。

## 5. Existing Project Example（既有项目示例）

假设一个新用户已经使用 Obsidian 三年，并存在：

```text
Vault/
├── Projects/
│   ├── Client-A/
│   ├── Research-X/
│   └── Personal-Website/
├── Notes/
└── Archive/
```

XINGSHU 不应复制整个 `Projects/`。

而应允许形成：

```text
XINGSHU Context References
├── Client-A
│   └── source -> Obsidian/Projects/Client-A/
├── Research-X
│   └── source -> Obsidian/Projects/Research-X/
└── Personal-Website
    └── source -> Obsidian/Projects/Personal-Website/
```

项目内容继续由 Obsidian 管理。

## 6. Refresh Semantics（刷新语义）

Context Reference 本身可以长期存在，但外部项目内容会变化。

因此 Reference 必须区分：

```text
reference identity = relatively stable
source content = mutable
```

用户询问当前状态时，XINGSHU 应根据 freshness policy 决定是否重新读取来源，而不是默认返回旧缓存。

例如：

```text
freshness_policy: resolve_on_query
```

或未来支持：

```text
resolve_on_query
metadata_refresh_interval
manual_only
source_event_triggered
```

缓存只能作为 Disposable Cache，不得自动成为 Source of Truth。

## 7. Reference Lifecycle（引用生命周期）

Context Reference 应支持：

```text
candidate
active
paused
source_unavailable
stale_locator
revoked
archived
```

典型情况：

- 用户移动了 Obsidian 项目文件夹；
- Git 仓库重命名；
- Drive 权限被撤销；
- 用户不再希望某个 AI 访问项目；
- 项目归档。

这些情况应更新 Reference 状态，而不是复制旧内容继续工作。

## 8. User-Controlled Registration（用户控制注册）

第一版建议采用：

> **discover automatically, register explicitly**
>
> 可以自动发现，但正式挂载需要明确确认。

原因：

- 扫描结果可能包含私人或无关项目；
- 文件夹名称不能可靠代表长期上下文意图；
- 自动注册可能造成意外 AI 可见范围扩张。

未来可以提供批量确认，但不得取消权限边界。

## 9. Relation to Memory（与记忆的关系）

挂载项目不等于建立长期记忆。

例如：

```text
Project Reference:
“用户存在 Project-A，正式来源位于 Obsidian/... ”
```

可以长期保留为 Context Anchor。

但：

```text
“Project-A 今天完成任务 27”
```

仍属于外部项目事实，默认不进入 XINGSHU Memory。

只有跨项目、跨时间仍然有长期价值的事实或习惯，才应通过现有 Memory Governance 独立评估。

## 10. Portability（可迁移性）

Context Reference 不应把用户永久绑定到某个知识软件。

例如用户将项目从 Obsidian 迁移到 Notion：

```text
Before
reference -> Obsidian / Projects/A

After
reference -> Notion / Project A
```

如果项目身份没有变化，则 AI 侧仍然可以使用同一个逻辑上下文名称。

因此：

> **AI 应依赖 XINGSHU 的稳定 Context Identity，而不是依赖某个应用的具体路径。**

## 11. Minimum Viable Onboarding（最小可行接入）

第一阶段只需要证明：

1. 用户授权一个只读 Source；
2. XINGSHU 可以发现至少一个已有项目候选；
3. 用户明确确认创建 Context Reference；
4. XINGSHU 不复制项目本体；
5. AI 可以通过 Reference 读取项目当前信息；
6. 原来源更新后，下次查询能得到更新后的结果；
7. 用户撤销 Reference 后，AI 无法再通过 XINGSHU 访问对应项目。

达到以上条件，才能说明 Existing Context Onboarding 的最小闭环成立。

## 12. Non-Goals（当前非目标）

本设计不意味着：

- 自动读取用户整个硬盘；
- 自动注册发现的所有项目；
- 将所有项目迁移进 XINGSHU；
- 自动把项目状态写成长久记忆；
- 无授权地扩大 AI 可访问范围；
- 依赖某一个固定知识库软件。

## Related

- [XINGSHU Context & Memory Bridge Architecture](CONTEXT_MEMORY_BRIDGE_ARCHITECTURE.md)
- [ADR-0001 — Source / Client Separation](ADR-0001-KNOWLEDGE-SOURCE-CLIENT-SEPARATION.md)
