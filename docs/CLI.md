---
type: public-runtime-documentation
system: xingshu-2.0
scope: public-core
status: candidate
version: 0.4-candidate
updated: 2026-09-15
governance_effect: none
authorization_effect: none
activation_effect: none
activation_state: not_active
visibility: public
---

# XINGSHU Validator CLI（验证器命令行）

XINGSHU-Core 提供 Read-Only Validator（只读验证器），读取一个 JSON Object（JSON 对象），按固定公开白名单选择 Legacy（旧记录）或 Context Bridge Candidate（上下文桥接候选）单对象验证，返回稳定的 Decision（决定）。

## 两个独立入口

| 入口 | 职责 |
|---|---|
| Existing Validator CLI（既有验证器命令行）：`xingshu doctor` / `xingshu validate` | 环境检查及既有单对象验证，不执行上下文 Runtime（运行时） |
| Candidate Runtime CLI（候选运行时命令行）：`python -m xingshu_core.runtime_cli resolve-local ...` | 所有者显式提供授权文件与本地 root，单次读取明确获准的 Markdown 入口 |

P4 v0.1 Candidate 暂不合并到现有 `xingshu` 主命令；没有新增 package entry point（包命令入口）。下文既有验证器的路线、JSON 策略、结果和退出码保持原义；独立 Runtime 的用法见本文末节和[专门说明](LOCAL_READ_ONLY_CONTEXT_RUNTIME.md)。

## 安装与命令

支持从仓库根目录进行 Editable Install（可编辑安装）：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

要求 Python 3.11+、`jsonschema>=4.23,<5` 和 `rfc3339-validator>=0.1.4,<1`。验证器不复制 Schema（结构合同）；旧记录使用 `schemas/v0.3/`，候选使用 `schemas/candidate/context-bridge/`，候选 `schema_version` 固定为 `context-bridge-candidate`。

```bash
xingshu --version
xingshu doctor
xingshu doctor --json
xingshu validate FILE.json
xingshu validate FILE.json --json
xingshu validate FILE.json --type memory_entry
xingshu validate FILE.json --type context_candidate --json
```

命令形状保持 `xingshu validate FILE [--type TYPE] [--json]`，不提供证据参数或链验证命令。

`doctor` 检查 Python、依赖、Repository / Schema Root（仓库及结构合同根目录）、三个 v0.3 Schema 和 `CORE_MANIFEST.yaml`。它继续使用 `registry.discover()` 并要求 `len(discovered) == 3`，只表示旧三路线就绪，不加载全部候选 Schema，不变成 18 或 19 条路线的健康检查。它不联网、不安装依赖、不修改仓库。

## 公开路线与分流

通用入口及 `--type` 精确支持以下 18 条路线，公开范围不由 Registry（结构注册表）动态发现：

| 判别字段 | 路线 | 唯一验证入口 |
|---|---|---|
| `record_type` | `memory_entry`、`knowledge_object`、`migration_provenance` | 原有三个旧记录验证器 |
| `object_kind` | `context_candidate`、`context_registration_proposal`、`context_validation_artifact`、`human_authorization_evidence`、`registered_context_reference`、`context_reference_transition` | `validate_context_bridge_object` |
| `object_kind` | `source_adapter_manifest`、`source_adapter_request`、`source_adapter_result`、`source_adapter_error` | `validate_source_adapter_object` |
| `object_kind` | `trusted_client_profile`、`runtime_binding` | `validate_authority_object` |
| `object_kind` | `resolve_context_request`、`resolve_context_result` | `validate_resolve_context_object` |
| `object_kind` | `derived_provider_metadata` | 私有、仅 Schema 检查的分支 |

后五行合计 15 条公开候选路线。`registered_context_reference` 固定进入 Context Bridge 单对象入口，不改走 Authority（权限资格）验证。

分流按字段是否存在判断，不使用字段值的真假性：

- 非对象保留旧 `record_not_object` 拒绝。
- 顶层同时存在 `record_type` 和 `object_kind`，无论值是否相同、为空或类型错误，都以 `candidate_discriminator_conflict` 拒绝。
- 仅存在 `object_kind` 时只进入候选路线。值必须是非空字符串且属于上述 15 条路线，否则以 `candidate_unsupported_route` 拒绝。
- 候选 `--type` 必须与 `object_kind` 精确匹配。库参数 `record_type_override` 沿用旧名作为显式路线选择器：只有 `None` 表示未指定；其他值必须是精确匹配的字符串，空字符串也触发 `candidate_route_mismatch`。
- 显式选择候选路线却缺少 `object_kind`，同样拒绝，不注入判别字段。
- 旧路线保留 `record_type_override or record.get("record_type")` 的选择语义。两种判别字段均缺失时，无 override（显式覆盖选择）保留 `unknown_record_type`；旧 override 继续由旧 Schema 判断输入。

检查顺序为：顶层对象 → 判别表示冲突 → 候选或旧路线 → override → 唯一验证入口。输入不被修改，任何验证失败都直接返回，不在候选、旧路线或不同候选验证器之间回退。同次调用复用同一个 Registry；已提供的实例原样传递。B/C/D/E 的结构及局部语义检查仅由既有单对象验证器完成，通用层不重复 Schema 验证。

`resolve_context_error` 为内部路线，不属于通用公开白名单：CLI 显式 `--type resolve_context_error` 返回用法错误及退出码 `4`；文件自动识别或 `validate_record()` 收到该 `object_kind` 时返回 `candidate_unsupported_route`、`REJECT`，退出码 `3`。既有 P2E 专用 API（程序接口）的内部支持能力保留。

## 原始 JSON 与重复键

`validate_file()` 仅解析一次，通过标准库 `json.loads(..., object_pairs_hook=...)` 为每个对象保留两个判别键的出现次数及普通字典的后值覆盖结果。计数不进入用户键空间。只检查根对象：顶层 `object_kind` 出现两次以上，或同时出现 `object_kind` 与 `record_type`，均返回 `candidate_discriminator_conflict`。重复值相同、不同或最后一个值看似合法都不能绕过检查；转义拼写在 JSON 解码后按同一键名计数。

纯旧记录没有顶层 `object_kind` 时，重复 `record_type` 保留 Last Value Wins（最后一个值生效）语义。普通键及嵌套重复键也保留既有行为；嵌套判别字段不计为顶层字段。这里不建立全局重复键拒绝策略。

完成根对象检查后，内部节点通过显式栈转换成普通 `dict/list` 再交给验证器。若不能安全保留或恢复元数据，返回安全错误，不丢弃元数据后继续。

`validate_record(parsed_mapping, ...)` 接收已解析的 Mapping（映射对象），无法恢复上游解析器已丢失的原始重复键。重复判别键保护只属于 `validate_file()` 的原始 JSON 边界。

## 决定、状态与退出码

| Decision | 退出码 | 含义 |
|---|---:|---|
| `PASS` | `0` | 所选路线的单对象检查通过；derived 路线只表示冻结 Schema 有效 |
| `NEEDS_REVIEW` | `2` | 记录可表达，但证据、状态或审查仍需复核 |
| `REJECT` | `3` | 结构、分流或语义检查不允许该记录 |
| `ERROR` | `4` | 输入错误、验证不可用或处理资源不足 |

结构有效不保证语义通过。例如 `active` Memory（记忆记录）使用陈旧证据时，Schema 可以有效，但 CLI 返回 `NEEDS_REVIEW`。

候选入口原样返回专用 `ValidationResult`（验证结果），保留 `object_valid`、`error_envelope_valid` 等状态，不统一改成 `accepted`。Source Adapter（来源适配器）错误信封的 `PASS/error_envelope_valid` 只证明信封有效，不表示来源操作成功。

下列六个跨证据 API 仅供显式库调用，通用 `validate_record`、`validate_file` 和现有 `xingshu` Validator CLI 不调用：

```text
validate_source_adapter_exchange
validate_registration_validation
validate_registration_chain
validate_reference_transition
validate_reference_authority
validate_resolve_context_exchange
```

## 结果模型

`--json` 继续序列化 `result.to_dict()`，顶层字段精确保持 `decision/status/record_type/schema_version/schema_ref/errors`。候选 `object_kind` 填入结果的 `record_type`，不新增 `object_kind` 或 `candidate_output` 输出字段。JSON 决定值保持小写，人类可读输出保留既有形式，不回显完整 Payload（载荷）。

```json
{
  "decision": "pass",
  "status": "current_valid",
  "record_type": "memory_entry",
  "schema_version": "0.3",
  "schema_ref": "schemas/v0.3/memory-entry.schema.json",
  "errors": []
}
```

`derived_provider_metadata` 成功时固定为 `PASS/object_valid`、`record_type=derived_provider_metadata`、`schema_version=context-bridge-candidate`、`schema_ref=schemas/candidate/context-bridge/derived-provider-metadata.schema.json`、`errors=()`。正常 Schema 不符时保留上述三项元数据，返回 `REJECT/rejected`，唯一问题为 `candidate_schema_invalid`，路径 `$`、消息 `object violates the frozen candidate schema`、`field=None`。不输出字段值、动态 Schema 路径、原始错误或派生数据。不新增公开的 derived 专用验证函数。

## 安全诊断

新增集成诊断精确为六种；所有新问题均 `field=None`，序列化不输出该字段：

| code | Decision / status | path | 固定 message |
|---|---|---|---|
| `candidate_discriminator_conflict` | REJECT / `rejected` | `$` | `top-level discriminator representation is ambiguous` |
| `candidate_unsupported_route` | REJECT / `rejected` | `$/object_kind` | `object kind is not supported by public validation` |
| `candidate_route_mismatch` | REJECT / `rejected` | `$/object_kind` | `object kind does not match the requested route` |
| `candidate_schema_invalid` | REJECT / `rejected` | `$` | `object violates the frozen candidate schema` |
| `candidate_validation_unavailable` | ERROR / `validation_unavailable` | `$` | `candidate validation is unavailable` |
| `validation_resource_limit_exceeded` | ERROR / `validation_unavailable` | `$` | `validation could not complete within available processing resources` |

分流拒绝、集成 ERROR 和文件边界错误的 `record_type/schema_version/schema_ref` 全部为 `None`；derived 的正常 Schema 拒绝除外。专用验证器既有结果直接保留。集成诊断不回显 `object_kind` 实际值、override、来源正文、定位符、ID、查询、Provider（能力提供方）、凭据或原始异常。

文件错误问题路径统一为 `$`，没有 `field`，不回显文件路径或正文：

| 条件 | Decision / status | code | message |
|---|---|---|---|
| 文件不存在或原有非文件判定 | ERROR / `input_error` | `input_file_missing` | `input file does not exist` |
| `JSONDecodeError` | ERROR / `input_error` | `invalid_json` | `JSON parsing failed at line {lineno} column {colno}`，仅包含行列号 |
| `UnicodeDecodeError` / `UnicodeError` / `OSError` | ERROR / `input_error` | `input_read_error` | `input file could not be read` |
| 解析器其他 `ValueError`，例如整数转换限制 | ERROR / `input_error` | `invalid_json` | `JSON parsing failed` |
| 读取、解析、节点转换或候选集成层的 `MemoryError` / `RecursionError` | ERROR / `validation_unavailable` | `validation_resource_limit_exceeded` | 上表资源错误固定消息 |

不设置任意文件大小上限，不截断输入后继续验证，也不把资源失败当成合同不合法。无法安全完成解析元数据检查或候选集成时，以固定 `candidate_validation_unavailable` 返回 ERROR。

任何 argparse（命令行参数解析器）用法错误均返回退出码 `4`，仅向 stderr（标准错误通道）输出以下三行及结尾换行，即使指定 `--json` 也一样：

```text
ERROR
status: input_error
message: invalid command-line usage
```

这是有意实施的用法诊断安全加固，不再输出 argparse 原始消息或无效参数值；正常验证输出结构和退出码保持兼容。

## 严格验证与只读边界

验证器通过 `Draft202012Validator.check_schema` 检查 Schema，并显式注入 `FormatChecker`（格式检查器）。RFC 3339 `date-time` 检查器必须接受有效带时区时间，拒绝无效日期、格式错误和无时区时间；检查器或依赖不可用时 Fail-Closed（无法验证即不放行）。

旧路线保留完整递归 `FORBIDDEN_KEYS` 检查：`payload`、`raw_payload`、`content`、`body`、`secret`、`credential`、`token`、`cookie`、`local_path`、`absolute_path`、`email`、`account_id`、`device_id`、`personal_identity`、`chat_text`。所有候选路线均不经过旧扫描，包括 `source_adapter_result`、`resolve_context_result` 和 derived；合法候选 `payload` 由冻结 Schema 与既有单对象验证器判断。

候选能力保持 disabled by default（默认禁用），`governance_effect=none`、`authorization_effect=none`、`activation_effect=none`。CLI 暴露单对象验证入口不等于 Runtime Activation（运行时激活），不启用服务、Gateway（网关）、来源适配器实现、网络、Provider 调用、凭据加载、Memory Store（记忆存储）或后台进程。验证只读取指定 JSON 文件及所需本地 Schema，不读取 JSON 中的来源定位符；不修改、移动或删除输入，不执行用户命令，不使用 `eval/exec`，不上传数据或访问账号。

单对象 PASS 不代表 Human Authorization（人类授权）、Registration Complete（登记完成）、Source Authoritative Observation Proof（来源权威观察证明）、Authority Eligible（权限资格成立）、Resolve Success（解析成功）、Runtime Active（运行时已激活）、Product Ready（产品就绪）或 Production Ready（生产就绪）。derived 的 PASS 仅证明冻结 Schema 有效，不证明来源已核验、当前来源事实、元数据具有权威性或运行时 Provider 可用。

## 独立 Candidate Runtime CLI

`local_read_only_context_runtime` 是独立 capability（能力），版本 `0.1`、`candidate`、disabled by default（默认关闭）、not active（未激活）；它不替换 `context_bridge_validation`，也不改变现有验证器行为。Manifest 登记没有治理、授权或激活效力。默认关闭是候选采用状态，不是阻止显式模块调用的功能开关。

在上述仓库可编辑安装环境中，可查看静态帮助；以下执行示例全部为占位输入：

```bash
python -m xingshu_core.runtime_cli --help
python -m xingshu_core.runtime_cli resolve-local --help
python -m xingshu_core.runtime_cli resolve-local \
  --reference ./reference.json \
  --client-profile ./client-profile.json \
  --runtime-binding ./runtime-binding.json \
  --request ./request.json \
  --root /absolute/path/to/synthetic-vault \
  --scope-id example-scope \
  --adapter-id example-localfs \
  --json
```

`--root` 必须是显式绝对物理目录路径，组件不能为符号链接。不能使用 `./synthetic-vault`，也不从 `source_locator` 推导 root。可选 `--max-bytes N` 设置 LocalFS 硬上限（1 至 1048576，默认 1048576），不改写请求文件。没有 force、skip-validation、自动登记或授权选项。

Host（宿主）对四份 JSON 使用严格 UTF-8、对象根和所有层级重复键拒绝策略，保留前三份授权文件的原始字节；这不改变上文既有 Validator 的 JSON 行为。

| Runtime 结果 | 独立退出码 | 输出 |
|---|---:|---|
| `SUCCESS` | `0` | JSON 模式 stdout 仅为 `resolve_context_result`；人类模式为 SUCCESS、resolved 及正文交付区 |
| validated `PROTOCOL_ERROR` | `2` | JSON 模式 stdout 仅为经 P2E 验证的 `resolve_context_error`；人类模式输出固定标题及错误码 |
| `LOCAL_EXECUTION_FAILURE` | `3` | JSON 模式 stdout 仅为 kind、固定 category/message；人类模式向 stderr 输出固定分类和消息 |
| Host / invocation error（宿主输入或用法错误） | `4` | 固定安全宿主错误；JSON 模式 stdout，人类模式 stderr |

这里的 `2` 不表示 Validator 的 NEEDS_REVIEW，`3` 也不表示 Validator 的 REJECT。协议错误、本地执行失败和宿主输入错误是不同边界，不能互换。用法错误不回显参数值或路径，正常 `--help` 只输出静态帮助。

成功正文是明确的交付内容；失败不附带正文、授权原始字节、绝对 root、凭据、异常或验证诊断。详见[执行链、候选安全边界、隐私和限制](LOCAL_READ_ONLY_CONTEXT_RUNTIME.md)。
