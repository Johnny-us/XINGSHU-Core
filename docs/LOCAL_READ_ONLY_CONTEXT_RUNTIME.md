---
type: public-runtime-documentation
system: xingshu-2.0
scope: public-core
status: candidate
version: "0.1"
updated: 2026-09-15
enabled_by_default: false
governance_effect: none
authorization_effect: none
activation_effect: none
activation_state: not_active
visibility: public
---

# Local Read-Only Context Runtime（本地只读上下文运行时）v0.1 Candidate

这是一个本地只读上下文解析候选：让已获明确授权的 AI 或 Local Tool（本地工具），通过所有者控制的宿主，从用户控制的 Source（来源）取得当前内容。它不是聊天软件、AI 模型、Obsidian 替代品或自动记忆数据库。

当前状态为 candidate（候选）、disabled by default（默认关闭）、not active（未激活），验证范围为 synthetic real-I/O validated（合成来源的真实输入输出已验证）。文件、测试通过、提交或能力登记都不产生治理、授权、采用或激活效力。

`CORE_MANIFEST.yaml` 的 `local_read_only_context_runtime` 与 `context_bridge_validation` 分别登记执行能力和验证能力。依赖关系表示使用既有验证合同，不自动启用依赖。默认关闭是候选采用状态；当前模块没有读取 Manifest 的激活开关，所有者显式调用仍可执行。停止使用的方式是停止调用独立 Host/CLI，不删除来源或修改授权记录。

## 已实现的执行链

```text
Owner-controlled Host（所有者控制的宿主）
→ RuntimeContext（运行上下文）
→ pre-read P2D（读取前权限资格验证）
→ LocalFS（本地文件系统适配器）
→ SourceAdapterExecution（响应与同次读取原始字节）
→ P2C（Source Adapter 交换验证）
→ post-read P2D（披露前权限资格复核）
→ P2E（最终 Resolve 证据验证）
→ transient Resolve result（瞬时解析结果）
```

Host 显式加载输入，构建冻结的 `LocalFilesystemSourceAdapter` 与 `RuntimeContext`，仅调用一次 `resolve_registered_context()`。Runtime 使用提供方中立的 `manifest()` / `execute()` 接口，没有 LocalFS 专用分支。资格成立后读取单个明确获准的本地 Markdown；返回正文前再次检查权限及最终证据，不重试。

内容指纹基于本次读取缓冲区的原始 bytes（字节），经 `exact_content_bytes` 传递；不通过重新编码文本制造观察证据。严格 UTF-8 解码保留 BOM、CRLF、非 ASCII 和尾部换行。宿主向 Runtime 和 LocalFS 注入同一个带时区的 UTC 时钟，并用 `p4e-localfs-` 加 UUID4 生成观测 ID；普通请求不能控制这些值。

P2D、P2C、P2E 是已有合同的资格、交换及证据验证，不代表操作系统身份认证或系统级隔离。

## 独立 CLI 与显式输入

环境要求为 Python 3.11+ 和仓库既有依赖；采用[CLI 文档](CLI.md)的仓库可编辑安装方式。LocalFS 需要提供 `dir_fd`、`O_NOFOLLOW` 等原语的 POSIX 文件系统环境，缺失时拒绝执行。现有 `xingshu doctor` / `xingshu validate` 继续只负责既有验证功能，P4 v0.1 不合并到该主命令，也不新增包命令入口。

```bash
python -m xingshu_core.runtime_cli resolve-local \
  --reference ./reference.json \
  --client-profile ./client-profile.json \
  --runtime-binding ./runtime-binding.json \
  --request ./request.json \
  --root /absolute/path/to/synthetic-vault \
  --scope-id example-scope \
  --adapter-id example-localfs \
  --max-bytes 1048576 \
  --json
```

以上都是合成占位路径，不能作为真实授权材料直接运行。`--root` 必须显式给出绝对物理目录，路径组件不能是符号链接，不自动展开相对路径、环境变量或 home。候选宿主不寻找 Vault、不扫描 root，也不创建授权文件。

| 输入文件 | 含义 |
|---|---|
| Registered Context Reference（已登记上下文引用） | 所有者控制的来源、入口、状态及策略记录 |
| Trusted Client Profile（可信客户端档案） | 所有者控制的客户端声明及有效期记录，不自行证明操作系统身份 |
| Runtime Binding（运行绑定） | 所有者控制的精确入口、传输选择及授权记录原始字节指纹关联 |
| Resolve Context Request（解析请求） | 普通调用请求，不能建立可信身份、root 或授权 |

Host 按以上顺序对四份文件各做一次二进制读取，严格 UTF-8 解码并解析 JSON，要求根对象且拒绝所有层级重复键，也拒绝 NaN/Infinity 和带 BOM 的 JSON；Source Markdown 的合法 UTF-8 BOM 则保留。解析失败仅返回固定宿主错误，不修复、合并、删字段或规范化值。

前三份 authority records（授权记录）的磁盘原始 bytes 原样进入 RuntimeContext。空白、键序和结尾换行都参与原始字节指纹；格式化文件可能使既有 Binding 不再匹配。Host 不重新序列化记录，不自动更新指纹；不提供手工绕过、force 或 skip-validation 方法。

`source_id` 从 Reference 派生，客户端选择从 Profile 的 `client_id` 派生，传输 ID/class 从 Binding 唯一派生，并继续经过 Runtime/P2D 检查。root、scope ID、adapter ID 和硬限额由显式 Host 参数提供；普通请求不能覆盖。`--max-bytes` 范围为 1 至 1048576（默认 1 MiB），实际读取还受请求的更小限额约束，Host 不改写请求。

## Source root 与 source_locator

`Reference.source_locator` 是逻辑 Source identity / root anchor（来源身份或逻辑根锚点），不是本机文件系统 root authority（根目录权限）。`--root` 才是所有者控制的 LocalFS 绑定，Host 不把 locator 转换为路径或从中推导 root。

允许入口仍受 `source_entry_points ∩ Runtime Binding bound_entry_points` 限制，并须满足其他权限、状态和策略检查。Reference 不授予 root 下所有文件的权限。v0.1 每次只处理一个明确入口，例如 `notes/photography.md`，不展开通配符或遍历目录寻找正文。

## Candidate Security Boundary（候选安全边界）

LocalFS 使用 `dir_fd`、`O_NOFOLLOW`、`O_DIRECTORY`、目录 device/inode 身份检查、普通文件检查、跨设备拒绝、硬链接拒绝、有界读取、文件前后稳定性检查，以及读取后从可信 root 对完整 locator namespace（定位符命名空间）的重新验证。

这些措施降低路径穿越、符号链接替换和部分 TOCTOU（检查与使用之间的竞态）风险。最终检查后仍存在一般文件系统并发的理论竞态窗口；不保证 atomic filesystem snapshot（原子文件系统快照）、恶意同用户文件系统隔离或恶意同进程隔离。不同授权文件各读取一次，也不构成跨文件原子授权快照。

宿主采用单用户、所有者控制的信任假设，不认证实际 OS caller（操作系统调用者）。所有者须保护配置文件、授权文件、宿主进程及输入在调用期间的稳定性。解析成功、对象结构有效和配置构造成功都不自动形成授权。

## Privacy Boundary（隐私边界）与退出码

成功正文是用户明确授权后的交付内容，可以出现在 SUCCESS stdout（标准输出）或 JSON response（JSON 响应）。默认人类输出仅有 SUCCESS、resolved 和正文区，不附加 root、授权文件路径、指纹或内部身份详情。

失败的 Host error、Runtime local failure 和 validated protocol error 不附带 Source 正文、authority raw bytes、绝对 root 路径、Python exception/traceback（异常与堆栈）、凭据或 validator diagnostics（验证诊断）。用法错误使用固定安全消息，不回显 argv 或参数值；正常 `--help` 仅展示静态帮助。

| 结果 | 退出码 | `--json` 输出 |
|---|---:|---|
| `SUCCESS` | `0` | stdout 仅 `resolve_context_result` |
| validated `PROTOCOL_ERROR` | `2` | stdout 仅经 P2E 验证的 `resolve_context_error`，无部分正文 |
| `LOCAL_EXECUTION_FAILURE` | `3` | stdout 仅 kind、固定 category 和 message |
| Host / invocation error | `4` | stdout 固定 `runtime_host_error` 结构 |

人类模式下协议错误显示固定错误码；本地失败和宿主错误向 stderr（标准错误）输出固定消息。协议错误、本地执行失败和宿主配置错误不能互换，也不使用既有 Validator 的 Decision（决定）语义。

`transient_only` 表示 Runtime 本身不将正文写入缓存或数据库；它不保证终端、shell history（命令历史）、重定向目标、调用方 AI 或操作系统不会保存输出。只读也不承诺操作系统不会更新文件 atime（访问时间）。

## 当前限制与未实现范围

- 每次 Resolve 仅一个明确授权入口，只读本地普通 Markdown（小写 `.md`）及严格 UTF-8；单文件读取上限为 1 MiB，LocalFS 配置或请求可进一步收窄。
- 仅支持 `verify_before_use` 和 `locator_and_verification`；不执行 `query_hint` / `disclosure_hints`，不做多入口 Runtime。
- 空 Source 观察可以通过 P2C，但不能成为 v0.1 成功 Resolve：返回 `LOCAL_EXECUTION_FAILURE / VALIDATION_FAILURE`。
- 缺失文件 `not_found` 和非法编码 `unsupported_encoding` 保留 `LOCAL_EXECUTION_FAILURE / SOURCE_FAILURE`。真实 `limit_exceeded` 只有 P2C 与 P2E 错误验证通过后才返回 `PROTOCOL_ERROR`。
- 披露前授权到期时，真实读取完成也必须拒绝交付；不把 Source 错误改报为其他错误来取得验证通过。
- 没有自动 Source 发现、登记或授权，没有搜索、semantic search（语义搜索）、embedding（向量嵌入）、summary（摘要）、自动 AI 记忆或跨应用记忆产品。
- 没有正文 cache（缓存）、数据库、会话历史、writeback（写回）、network Source（网络来源）、MCP、Obsidian integration（集成）、daemon（常驻进程）或 background watcher（后台监听）。不适用于网络挂载或会触发下载的占位文件。
- 没有 OS 身份认证、恶意同用户或同进程隔离、原子文件系统或跨文件授权快照；授权及配置文件须由所有者保护。Candidate 默认关闭、未激活。

## 可重复验证与发布边界

真实执行证据来自临时合成 Markdown 与授权文件，经过原有 P2D/P2C/P2D/P2E；不使用 Fake Adapter（模拟适配器）替代集成主链。覆盖原始字节、同路径内容更新、权限拒绝、限额、失败隐私和无写回。该证据不等于生产环境验证或真实私人 Vault 集成。

在已安装测试依赖的仓库环境中运行：

```bash
python -m xingshu_core.runtime_cli --help
python -m xingshu_core.runtime_cli resolve-local --help
python -m pytest tests/runtime/test_runtime_host.py tests/runtime/test_runtime_cli.py -v --import-mode=importlib
python -m pytest tests/ -v --import-mode=importlib
git diff --check
```

完整 P4 分阶段测试和重点回归命令见[测试索引](../tests/README.md)。所需依赖来自现有 `requirements-test.txt`，不增加新依赖。

Candidate Publication Readiness（候选发布准备度）通过只表示可以请求所有者授权下一步 GitHub Publication Micro-Batch（小批次发布）。本地候选检查点不表示已经发布、激活、采用或完成产品交付；push、PR、merge、tag、release 仍需独立授权。
