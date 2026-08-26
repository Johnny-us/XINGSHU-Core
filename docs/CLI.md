---
type: public-runtime-documentation
system: xingshu-2.0
scope: public-core
status: candidate
version: 0.4-candidate
updated: 2026-08-27
governance_effect: none
activation_state: not_active
visibility: public
---

# XINGSHU Validator CLI（验证器命令行）

XINGSHU-Core v0.4 提供一个 Read-Only Runnable Validator（只读可运行验证器）。它读取一个 JSON Object（JSON 对象），依次执行 JSON Parsing（解析）、现有 v0.3 Schema Validation（结构验证）、Semantic Validation（语义验证），最后返回稳定 Decision（决定）。

## Install（安装）

第一版正式支持从仓库根目录进行 Editable Install：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

要求 Python 3.11+ 和 `jsonschema>=4.23,<5`。Runtime 不复制 Schema；Canonical Schema 仍位于 `schemas/v0.3/`。

## Commands（命令）

### Version（版本）

```bash
xingshu --version
```

### Doctor（本地就绪检查）

```bash
xingshu doctor
xingshu doctor --json
```

Doctor 检查 Python、`jsonschema`、Repository / Schema Root、三个 v0.3 Schema 和 `CORE_MANIFEST.yaml`。Doctor 不联网、不安装依赖、不修改仓库。

### Validate（验证）

```bash
xingshu validate FILE.json
xingshu validate FILE.json --json
xingshu validate FILE.json --type memory_entry
```

CLI 默认读取 `record_type` 自动选择 Schema。`--type` 只用于显式选择已有支持类型；它不会补写或修改输入记录。

当前支持：

- `memory_entry`
- `knowledge_object`
- `migration_provenance`

## Decision and Exit Codes（决定与退出码）

| Decision | 退出码 | 含义 |
|---|---:|---|
| `PASS` | `0` | Schema 与语义检查通过 |
| `NEEDS_REVIEW` | `2` | 记录可表达，但证据、状态或审查仍需复核 |
| `REJECT` | `3` | Schema 或 Fail-Closed 语义不允许该记录 |
| `ERROR` | `4` | 文件缺失、JSON 无法解析或工具环境不可用 |

Schema Valid（结构有效）不保证 Semantic PASS（语义通过）。例如 `active` Memory 使用陈旧 Evidence 时，Schema 可以有效，但 CLI 返回 `NEEDS_REVIEW`。

## Result Model（结果模型）

`--json` 返回：

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

错误只返回必要的 `path`、`field`、`code` 和安全消息，不回显完整输入 Payload（载荷）。

## Schema Discovery（Schema 发现）

默认从 Editable Install 所在仓库的 `schemas/` 读取 Canonical Schema。高级场景可以设置 `XINGSHU_SCHEMA_ROOT` 指向仓库根或 `schemas/`，但普通 Clone + `pip install -e .` 无需配置。

## Read-Only Boundary（只读边界）

Validator 不修改、移动或删除输入文件；不写入 Memory Store；不执行用户命令；不使用 `eval` / `exec`；不加载任意 Python；不联网、调用 API、上传数据或访问账号。程序可以运行不等于 Governance Active、Adoption、Release 或现实动作 Authorization。
