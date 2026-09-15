---
type: public-bridge-scope-contract
system: xingshu-2.0
scope: public-core
status: candidate
version: "0.1"
updated: 2026-09-15
phase: P5D
implementation_state: candidate_implemented
validation_scope: synthetic_vault_real_io
enabled_by_default: false
activation_state: not_active
governance_effect: none
authorization_effect: none
activation_effect: none
visibility: public
---

# Obsidian Bridge（Obsidian 桥接）v0.1 范围与组合合同

## 1. Purpose（目的）与冻结基线

本规格冻结 Obsidian Vault（知识库目录）作为 XINGSHU Source（来源）的最小接入范围与组合接口。目标是 `Obsidian → XINGSHU`，保留用户控制的原始文件，不复制整个 Vault，不建立第二数据库。

本文件保留 P5A 冻结规范，并记录已完成的 P5B 候选实现与 P5C 合成集成证据。当前为 P5D 本地候选包装；不改变执行语义、Schema（结构合同）或 CLI（命令行接口），不产生能力启用或私人实例采用效力。Manifest（能力清单）登记见第 18 节。

| 基线 | 值 |
|---|---|
| Repository（仓库） | `Johnny-us/XINGSHU-Core` |
| 已合并 P4 main | `7d4de3ace2efd723e2f76c9400248a8b89efd54e` |
| P4 tree | `4abb93a7d9688bb8846ac71c67a5590eddf05b44` |
| P4 Candidate | `40166eeb61274e09da08eea5ec29a3661fdd808d` |

P4 的完整边界见 [Local Read-Only Context Runtime](LOCAL_READ_ONLY_CONTEXT_RUNTIME.md)。P4 已支持已落地的普通本地 Markdown；本规格增加 Obsidian 笔记准入约束，不改写通用 Runtime（运行时）。

## 2. Non-goals（非目标）

v0.1 不实现解析器、插件、Vault 或笔记发现、目录授权、索引、搜索、embedding（向量嵌入）、摘要、自动记忆提取、附件、Canvas、递归链接展开、缓存、写回、后台任务或网络 Source。

不实现 ChatGPT、Claude、DeepSeek、MCP、HTTP、Connector（连接器）或 AI gateway（智能体网关）。`XINGSHU → AI clients` 属于后续独立客户端桥接阶段。

## 3. P4 reuse boundary（复用边界）

正式结构为：

```text
Owner-controlled Obsidian Bridge（所有者控制的桥接层）
↓
P4 Host Composition Boundary（宿主组合边界）
↓
P4 Runtime
↓
Obsidian note admission wrapper（笔记准入包装器）
↓
P4 LocalFilesystemSourceAdapter
↓
Vault Markdown
```

实际成功链必须保留：`RuntimeContext → pre-read P2D → wrapper → LocalFS → exact_content_bytes → P2C → post-read P2D → P2E → transient-only result`。P2D 为权限资格验证，P2C 为来源交换验证，P2E 为最终 Resolve（解析）证据验证。

冻结复用 `LocalFilesystemSourceAdapter`、`resolve_registered_context`、`RuntimeContext`、`SourceAdapterExecution`、既有 P2D/P2C/P2E、原始来源字节与瞬时结果。P5 不创建第二套 filesystem reader（文件读取器）、路径包含性检查、SHA-256 实现、TOCTOU（检查与使用竞态）处理或 Resolve 协议。

继承 P4 的单入口、严格 UTF-8、最多 1 MiB（可进一步收窄）及最多 32 层中间目录限制，只支持 `verify_before_use` / `locator_and_verification`。P5 不截断正文或放宽限额；空文件仍不能产生成功 Resolve。固定内容指纹不匹配仍失败，无固定指纹时每次读取当前文件内容。

包装器拒绝时不产生来源交换或成功结果，不伪造 P2C/P2E 回执；正常委托结果必须继续经过全部既有成功门禁。

## 4. Identity / location ownership（身份与位置所有权）

| 概念 | 所有权与约束 |
|---|---|
| Vault Root | `LocalRuntimeHostConfig.source_root`，所有者显式给出的绝对物理目录；由 P4 检查，不进入普通 Resolve 请求或协议响应 |
| Source Locator | `Reference.source_locator`，保持 opaque（不透明）的逻辑来源锚点；可表达未来由所有者分配的 Vault 身份，不是本地路径或根目录权限 |
| Note Entry | 含小写 `.md` 后缀的 Vault 相对精确路径，例如 `Projects/XINGSHU.md`；受 `reference.source_entry_points ∩ runtime_binding.bound_entry_points` 及其他 P2D 条件限制 |

不得从 Source Locator、Vault 显示名称、笔记正文、URI 或普通请求自动推导 root。一个显式调用使用一个所有者接受的 Source/root 绑定；这种本地绑定不自行建立授权。

Reference 与 Binding 的入口保留既有顺序和最多 8 项的合同；每次 Resolve 仍只能选一项。多项授权时必须显式选择其中一项，不静默选择第一项或批量读取。不允许 glob（通配符）、目录前缀、递归 scope（作用域）、模糊名称或 alias lookup（别名查找）。

## 5. Trust ownership（信任所有权）

所有者控制 Host 配置、四个输入文件、来源根目录、时钟、适配器及宿主进程。普通请求只能在已接受入口中收窄选择，不能控制可信身份、root、adapter composer（适配器组合函数）或准入策略。

P4 Host 继续独占输入加载与 `RuntimeContext` 构造。Reference、Profile、Binding 各自的原始 bytes（字节）原样交接；不得序列化、排序、去换行或修复后当作原始权限字节。Request 与这些权限对象由同一次 Host 加载流程提供。

同一调用中输入按现有只读所有权约定保持稳定。该约定不是恶意同用户或同进程隔离；各文件读取一次也不是跨文件原子快照。

## 6. Note admission / hidden configuration policy（笔记准入与隐藏配置规则）

P5 包装器在委托 LocalFS `execute()` 前，只对其收到的同一个 `target_locator` 执行以下附加规则：

1. 必须是字符串并以小写 `.md` 结尾；不补后缀，不接受 `.MD`。
2. 按字面 `/` 分隔的任意路径组件不得以 `.` 开头。

因此 `.obsidian/config.md`、`.hidden/note.md`、`folder/.private.md` 全部拒绝。判定只针对定位符字符串，不识别所有平台级 hidden attributes（隐藏属性）。Obsidian 默认配置目录为 `.obsidian`，也支持其他以点号开头的配置目录名称；见 [Obsidian Configuration folder](https://obsidian.md/help/configuration-folder)。

本规则是 P5 准入限制，不修改通用 LocalFS 对隐藏 Markdown 的行为。准入通过仍不证明路径安全：绝对路径、空组件、反斜线、百分号编码、符号链接、设备、文件类型、硬链接及限额等继续由 P4 检查。

不 URL decode（网址解码）、不规范化路径、不展开变量、不将 `../` 修复成其他入口。`../` 因点号组件也可能先触发 P5 拒绝；不得为了得到某个 Source 错误码而绕过准入。所有拒绝均须发生在笔记正文读取之前。Host 构造 LocalFS 时已有的根目录元数据访问可以先发生，不宣称拒绝前完全没有文件系统访问。

## 7. Content semantics（内容语义）与链接边界

成功时原样交付整篇已授权 Markdown，包括 YAML frontmatter（文件头属性）、properties（属性）、tags（标签）、aliases（别名）、wikilinks（双括号链接）、Markdown links、embeds（嵌入）、heading links（标题链接）及 block references（块引用）。不解析、不执行、不剥离、不重排这些内容。

`[[Other Note]]`、`![[Other Note]]`、`[[Note#Heading]]`、`[[Note#^block]]` 和 `![[image.png]]` 只作为当前笔记正文中的普通字符串。它们不得触发第二次文件读取、扩大 scope、建立 authority（授权）、选择 Source、覆盖 root 或建立可信身份。普通 Resolve 入口仍是精确路径，不增加 Obsidian 链接选择器。

frontmatter 中的 `xingshu_allow: true` 没有授权效力。未来解析出的属性只能成为描述性元数据或待接受的 proposal（提案），不能成为授权证据或可信来源选择依据。

`link expansion depth = 0` 是概念合同，不新增请求字段、配置参数或可由 caller（调用者）打开的隐藏开关。标题与块引用不构成片段读取功能；不把片段选择请求自动改成整篇读取。

## 8. Discovery / plugin / media boundaries（发现、插件与媒体边界）

| 能力 | v0.1 |
|---|---|
| Vault discovery | NONE |
| Note discovery | NONE |
| Folder authorization | NONE |
| Vault indexing / search | NONE |
| Obsidian Plugin API | OUT OF SCOPE |
| Attachments / Canvas / non-Markdown | unsupported |

不得扫描 Home、Documents、iCloud、Obsidian 全局配置、最近 Vault 列表或 Vault 目录。只允许 P4 对精确根/入口做已有元数据遍历和单文件读取；这不构成目录枚举。

图片、PDF、音频及 `.canvas` 均不读取；正文中的附件引用不展开。v0.1 根据精确路径与内容类型工作，不扫描文件夹来猜测文件的用途。

未来插件只能作为 UX / control surface（交互与控制界面）：选择笔记、提交授权提案、请求暂停/撤销、显示状态；权限真相仍由 XINGSHU 接受的 authority records（授权记录）决定。插件不自行授予权限。

## 9. Rename / case / Unicode（改名、大小写与字符行为）

v0.1 授权的是 exact path entry（精确路径入口），不是长期 inode 身份。不提供 rename tracking（改名追踪）：`Projects/A.md` 改为 `Projects/B.md` 后，旧授权不会转移到 B，须重新接受入口和相关权限记录。Vault 根路径变化也须由所有者重新接受本地绑定，不自动定位新目录。

若旧 A 路径后来被另一普通文件占用，且权限未固定 `content_fingerprint`，后续 P4/P5 调用可能读取新的 A 内容，不能声称改名后必然 `not_found`。P4 的 inode 稳定性和命名空间重验针对单次读取及适配器当前绑定，不提供跨 Host 重建的永久笔记身份。

定位符按 exact string comparison（精确字符串比较）授权，不做 case folding（大小写折叠）、Unicode normalization（字符规范化）、模糊匹配或别名解析。底层文件系统不一定隔离 `A.md` 与 `a.md`；不得通过扫描目录补偿或宣称跨平台名称隔离。

## 10. Host composition problem（宿主组合问题）与方案比较

基线 `runtime_host.resolve_local()` 在内部依次加载 Reference、Profile、Binding、Request，直接构造 LocalFS 和 `RuntimeContext`。当前没有公开的组合参数。

| 方案 | 结论 |
|---|---|
| P5 预读四文件后调用 `resolve_local()` 重读 | 拒绝：双重快照、检查/执行漂移和字节所有权不清 |
| P5 导入 `_load_json` 或复制加载、Context 构造和 Runtime 编排 | 拒绝：私有接口耦合或第二套执行链 |
| 在通用 Runtime/LocalFS 加 Obsidian 分支 | 拒绝：污染冻结的提供方中立/通用读取边界 |
| 注入任意原始 adapter factory，接管根目录和来源构造 | 不选：暴露过多配置和构造责任，允许脱离既有 LocalFS |
| 在 Host 构造好 LocalFS 后注入可信 adapter composer | **唯一推荐**：保留一次加载与默认行为，P5 只包装实际执行适配器 |

## 11. Selected API（已实现的冻结组合接口）

P5B 已在 `runtime_host.py` 完成 additive extension（增量扩展）。冻结签名为：

```python
SourceAdapterComposer = Callable[[SourceAdapter], SourceAdapter]

def resolve_local(
    config: LocalRuntimeHostConfig,
    *,
    clock: TrustedClock | None = None,
    observation_id_factory: Callable[[], str] | None = None,
    adapter_composer: SourceAdapterComposer | None = None,
) -> RuntimeExecutionResult:
    ...
```

`Callable` 来自 `collections.abc`；`SourceAdapter`、`TrustedClock` 与 `RuntimeExecutionResult` 复用 `runtime_contracts` 的公开类型。`SourceAdapterComposer` 为 `runtime_host` 的公开类型别名；不修改冻结的 `SourceAdapter` Protocol（接口约定）。上述省略号只省略实现正文；P5A 冻结的签名已由 P5B 实现。

组合点与所有权必须满足：

1. P4 Host 按原顺序各加载四个输入文件一次，不改变加载器和原始字节处理。
2. Host 用原配置先构造真实 LocalFS，再在构造 `RuntimeContext` 前调用 composer，非空时每次 Host 调用恰好一次。
3. composer 唯一参数是已构造的 `SourceAdapter` 对象；不另传权限对象、原始权限 bytes、Request 或配置文件路径。
4. `adapter_composer=None` 时直接使用原 LocalFS，完全保留旧默认路线。
5. composer 必须可调用且返回符合既有 `RuntimeContext` 适配器形状要求的对象；组合异常或无效返回值走既有固定 `HostInputError`，不得静默回退到无策略 LocalFS。
6. Host 仍是唯一 Context 构造者，原始权限 bytes、时钟、身份与传输选择原样交接；然后只调用一次既有 Runtime。
7. 参数只给可信 Host-only library caller（宿主库调用方）。不进入 `LocalRuntimeHostConfig`、四份 JSON、CLI 参数、环境变量或动态模块导入配置。

这是可信 Python 代码组合接口，不是插件沙箱。`SourceAdapter` 形状检查不能认证实现；具有任意同进程代码执行能力的 Owner 控制面本就可以改变执行方式，不能声称 hook 隔离恶意 Host。

P5 已实现的唯一公开执行入口为：

```python
def resolve_obsidian(
    config: LocalRuntimeHostConfig,
    *,
    clock: TrustedClock | None = None,
    observation_id_factory: Callable[[], str] | None = None,
) -> RuntimeExecutionResult:
    ...
```

它位于 `obsidian_bridge.py`，只调用一次公开的 `resolve_local()`，始终传入内部固定 P5 composer；不暴露关闭策略或替换 composer 的参数。配置、时钟、ID 工厂都保持可信 Host 所有权，不从 Request 提取。不得自己预读四文件、构造 Context 或调用私有 helper。

内部 wrapper（包装器）的 `manifest()` 原样委托已有 LocalFS manifest，不冒充新的操作或协议版本。`execute(request)` 对同一请求的不可变 locator 字符串执行第 6 节准入，拒绝则不调用 delegate；通过则将同一请求原样委托一次，原样返回 `SourceAdapterExecution`，不读取、编码、散列、解析或持久化正文。不得保留请求/结果历史，repr（调试表示）不得暴露 delegate 内部配置。

P5 policy 检查的是 Runtime 在 P2D 通过后从本次输入快照选出的实际 `target_locator`，不是另一次加载得到的预览值。未授权路径不会因 wrapper 获得权限；普通请求不能选择无 wrapper 路线。

## 12. Failure semantics（失败语义）

**P5-specific admission failure 唯一选定分类：`RuntimeFailureCategory.SOURCE_FAILURE`，结果种类 `LOCAL_EXECUTION_FAILURE`。**

理由：冻结 `context_runtime.resolve_registered_context()` 在 `adapter.execute(sent)` 前将当前失败分类设为 `SOURCE_FAILURE`，并把该调用抛出的异常转换成固定本地失败。此处表达受选适配器无法完成来源操作，不是 Source 协议 `error_code`，也不宣称文件不存在或编码有错。

包装器准入拒绝须抛出一个仅含固定安全消息的私有异常；不返回伪造的 `source_adapter_error`，不把 `RuntimeExecutionResult` 作为适配器响应。Runtime 使用现有消息 `Source operation could not be completed.`，不附正文、locator、root 或底层异常。

| 失败发生处 | 对外语义 |
|---|---|
| P5 点号组件/扩展名准入拒绝 | 既有 `LOCAL_EXECUTION_FAILURE / SOURCE_FAILURE`；delegate 执行次数为 0 |
| Host 加载、配置、composer 构造失败 | 既有固定 `HostInputError` |
| P2D、P2C、P2E 或 LocalFS 原有失败 | 完全保留 P4 现有分类和真实协议映射 |

不选择 `INVALID_INPUT`：要在 adapter 执行层得到这一不同分类，需要改冻结 Runtime 的错误路由或事后重映射，扩大范围。P5 不把所有 `SOURCE_FAILURE` 重新解释成准入失败，也不把下游真实错误改码。

准入拒绝不重试、不部分返回、不伪装为 `not_found`、`unsupported_encoding`、`limit_exceeded` 或成功验证。无需新增异常公开 API、Protocol Error Schema 或 `RuntimeFailureCategory` 枚举。

## 13. Schema / capability / compatibility（结构、能力与兼容）

**NO NEW JSON SCHEMA。** Reference、Profile、Binding、Source Adapter 和 Resolve 已表达现有协议；root 与 composer 仅属于 Host 进程内配置，没有新持久化/跨进程对象。若后续发现确需新增协议对象，须停止扩展并另行评审。

P5D packaging（能力包装）独立登记 `obsidian_context_bridge`，依赖 `local_read_only_context_runtime >= 0.1`，保持 `additive_optional`、`candidate`、`enabled_by_default: false`、`activation_state: not_active` 和三个 effect 为 `none`。P5A 的范围冻结未修改 Manifest；P5D 的独立登记不把 P4 改名为 Obsidian Runtime。

旧 `resolve_local(config, clock=..., observation_id_factory=...)` 调用不变。原 `LocalRuntimeHostConfig` 字段不变；通用 Runtime、LocalFS、验证器、Schema、现有 `xingshu doctor` / `xingshu validate` 和独立 P4 CLI 不依赖 Obsidian，也不暴露新开关。

默认关闭是候选采用状态，不宣称存在尚未实现的强制激活开关。P5 不自动激活 P4 依赖。

## 14. P5B production scope（已实现生产代码范围）

P5B 最小生产代码仅涉及：

- `src/xingshu_core/runtime_host.py`：第 11 节公开类型别名、可选组合参数、单次组合点及既有安全宿主错误处理。
- `src/xingshu_core/obsidian_bridge.py`：固定组合入口、内部准入 wrapper 与固定私有拒绝异常。

不创建新的 reader、parser、hash helper、authority loader、Context builder、CLI 或插件。P5B 已按独立授权完成单元测试和最小真实链；本规格不授予额外实现权限。

## 15. P5C synthetic E2E matrix（合成端到端验收矩阵）

P5C 测试使用 `tmp_path` 合成 Reference/Profile/Binding/Request、Vault 及邻居哨兵。不得接触真实 Vault。证据包装必须调用原实现，不能 mock 成功结果、LocalFS 读取或 P2D/P2C/P2E。

| 场景 | 必须验证 |
|---|---|
| 正常获授权笔记 | `resolve_obsidian → resolve_local → Runtime → wrapper → LocalFS → P2C → post-read P2D → P2E` 成功，正文与磁盘一致 |
| 授权文件不同空白/键序/尾部换行 | 四文件各加载一次，前三份原始 bytes 原样进入 Context；wrapper 不产生第二次加载 |
| frontmatter / wikilink / embed / heading / block | 文本原样保留，不因内容触发第二次读取；`xingshu_allow: true` 不产生权限 |
| 链接到私人邻居 | 邻居正文读取次数为 0，不扫描目录，不返回邻居哨兵 |
| `.obsidian/*.md`、其他 `.hidden/*.md`、`folder/.private.md` | P5 本地 `SOURCE_FAILURE`，LocalFS delegate `execute` 为 0，不泄漏路径/正文 |
| 非 Markdown、`.MD`、附件、`.canvas` | 拒绝且无正文读取，不改写扩展名 |
| symlink / hardlink | 由真实 P4 拒绝，不添加 P5 文件系统实现 |
| `../`、百分号编码、非法分隔符 | fail closed（默认拒绝），不解码、不规范化、不修复 |
| BOM / CRLF / 中文 / 尾部换行 | 来源 raw bytes、正文与指纹证据保持 P4 精确语义 |
| 同一路径内容 A → B | 未固定指纹时下一次读取 B；不重登记、不缓存、不重试 |
| 固定内容指纹后内容变化 | 不返回成功，保留 P4 失败语义 |
| Note rename | 不追踪新路径；旧路径缺失时失败，不扩大权限 |
| 旧路径重新占用 | 未固定指纹时允许依既有路径授权观察新内容，不宣称持久 inode 绑定 |
| paused / revoked / expired | 真实 P2D 拒绝，笔记正文不读取 |
| post-read expiry | 原始读取发生但不披露正文，保持第二次 P2D 门禁 |
| composer ownership | 默认 None 不调用 hook；非空只调用一次；异常/无效返回不回退；JSON/CLI 不可选择 hook |
| P4 非 Obsidian 兼容 | 不传 composer 时普通本地 Markdown 与已授权隐藏 Markdown 保留既有行为 |
| 输入稳定与隐私 | 不修改请求、权限对象/字节、文件；异常、repr、失败结果无路径/正文/权限 bytes |

已实现测试位于 `tests/runtime/test_obsidian_bridge.py`、`tests/runtime/test_obsidian_bridge_localfs_integration.py`，合成支持为 `tests/support/obsidian_bridge_fixtures.py`；现有 `tests/runtime/test_runtime_host.py` 已增补默认路线与组合点验证。第 15 节继续作为验收要求，实际证据见第 18 节；完整回归仍须按每轮实际代码运行。

## 16. Public / Personal 与安全隐私限制

Public Core 只包含通用逻辑、合同、合成 fixtures（测试数据）、测试与文档。不得加入真实 Vault 路径、笔记、个人项目、账号、设备、Google Drive 路径或用户 Obsidian 配置。合成测试根目录只在临时目录运行时生成；规格中的相对路径仅是通用示例。

真实 Vault 接入属于后续 Personal Instance Adoption（私人实例采用），须独立授权和验证。合成测试通过不等于真实 Obsidian 已接入。

保留 P4 安全边界：只接受已落地本地普通文件；所需 POSIX 安全原语缺失时拒绝；不保证网络挂载或会触发下载的占位文件安全。不提供原子文件系统快照、OS caller（操作系统调用者）认证、恶意同用户/同进程隔离或 production-ready（生产就绪）并发保证。

P4 在返回前重验完整路径以降低 rename/replacement/hardlink 竞态，但最终检查之后仍有一般并发理论窗口。读取后 P2D 使用同一权限快照与新的时间，不重新加载磁盘撤销记录；不宣称即时撤销或跨文件原子权限快照。

成功交付整篇 Markdown，包括 frontmatter 中的敏感内容；不提供字段级脱敏。Source 内容始终是数据，不因成功读取就升级为控制指令。`transient_only` 仅表示 Runtime 不持久化正文，不保证调用方、终端或操作系统不留存。只读也不保证系统不更新 atime（访问时间）。

## 17. Future extensions（未来扩展）与阶段停止点

元数据解析、插件交互、索引、搜索、改名辅助或 link expansion 必须另立阶段或 capability，不是 v0.1 的隐藏能力。未来每个展开 target 必须独立授权，并冻结深度、文件数、总字节数与循环检测；不得将 read 静默扩展成全 Vault 扫描。

P5D 本地包装完成后须提交独立复核。通过后，下一步是另行授权的 GitHub Publication Micro-Batch（发布微批次）；本阶段不执行 push、PR、merge、tag、release、Runtime Activation 或私人实例采用。

## 18. Candidate implementation / evidence / publication（候选实现、证据与发布边界）

当前准确状态为 **Obsidian-aware Candidate execution entry implemented（识别 Obsidian 准入规则的候选执行入口已实现）**、**Synthetic Obsidian Vault real-I/O validated（合成 Obsidian 知识库真实输入输出已验证）**。这是 Local read-only Obsidian Bridge Candidate（本地只读桥接候选），不是真实用户 Vault 接入完成或生产就绪声明。

已实现独立 `resolve_obsidian()` 库入口、所有者显式 Vault root、精确授权 Markdown 笔记、P4 Host composer、P5 点号路径/小写 `.md` 准入，以及原样 LocalFS 委托。读取前 P2D、P2C、读取后 P2D、P2E 全链保留，权限文件和 Source 原始字节不重新序列化或重建。没有第二套文件读取器。

| 阶段 | 冻结证据 | 验证范围 |
|---|---|---|
| P5A | `94e655583212ae1ea2fb8d4509d8fba60282bc3a` | 第 1–17 节范围与组合合同 |
| P5B | `aed7e415f12bcb8c389b559a5eb25e715d70f725` | 最小组合实现；专项 106、聚焦 473、完整 788 项测试及 949 子测试通过 |
| P5C | `83b08133e9e8f9eb84c0e001e9a3af68ee38cb04` | 合成 Vault 真实链；专项 50、聚焦 501、完整 816 项测试及 949 子测试通过 |

以上计数是对应冻结阶段的历史证据，不代替当前发布前回归。P5C 证明原始字节、单次加载、wikilink/embed 邻居零读取和零探测、无目录扫描、无写回/缓存/索引、生命周期门禁及错误语义。所有 Public Core Vault 测试只使用 synthetic `tmp_path`；没有读取用户真实 Obsidian。真实接入属于独立的 Personal Instance Adoption，须后续单独授权。

明确未实现或不提供：真实用户 Vault 采用；自动 Vault/笔记发现、目录授权、Vault 搜索、全库索引、语义搜索、embeddings、摘要；metadata/YAML/frontmatter 语义解析、别名解析、wikilink/embed 展开；附件、Canvas、Obsidian 插件、watcher/daemon（监视器/后台服务）、写回；OS 调用者认证、恶意同用户/同进程隔离、原子文件系统快照、磁盘撤销记录即时重载；ChatGPT、Claude、DeepSeek 集成、MCP、HTTP/API gateway；生产就绪保证。

`resolve_obsidian()` 仅为 Python library entry。现有 `python -m xingshu_core.runtime_cli resolve-local` 仍是 P4 通用 Local Runtime CLI，不使用 P5 composer，不自动进入 Obsidian 模式；没有新增 `--obsidian`、`--vault` 或 `--allow-hidden` 参数。

Manifest 新增独立 `obsidian_context_bridge`，保持 v0.1、candidate、默认关闭、无治理/授权/激活效力，依赖 `local_read_only_context_runtime >= 0.1`。`schema_refs` 复用实际参与运行的 Reference、Profile、Binding、Source Adapter、Resolve 五份既有合同，不存在新的 Obsidian Schema。`test_refs` 只登记真实可执行测试，不包含支持夹具。既有 `context_bridge_validation` 与 `local_read_only_context_runtime` 元数据不变；依赖不自动激活任何能力。

本地提交、文档更新、测试通过或 Manifest 登记不构成 GitHub 发布授权。本阶段停止于独立复核；后续 push/PR、merge、tag、release、Runtime Activation 和真实 Vault 采用分别受其授权边界约束。
