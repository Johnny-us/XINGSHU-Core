---
type: public-release-notes
system: xingshu-2.0
scope: public-core
status: candidate
version: 0.4-candidate
updated: 2026-08-27
governance_effect: none
activation_state: not_active
visibility: public
---

# XINGSHU-Core v0.4 Change Notes（变更说明）

## Status（状态）

v0.4 是 Runnable Core / Validator CLI Candidate（可运行核心 / 验证器命令行候选）。Runnable（可运行）不等于 Active Governance（治理已激活），不构成 Adoption、Release 或 Personal Instance 自动接入。

## Added（新增）

- Python 3.11+ 的 `xingshu-core` 可编辑安装包；
- `xingshu --version`、`xingshu doctor`、`xingshu validate`；
- `pass / needs_review / reject / error` 统一 Decision 与 `0 / 2 / 3 / 4` 退出码；
- 从现有 v0.3 测试提炼出的 Memory、Knowledge Object 和 Migration Semantic Validators；
- 读取现有 `schemas/v0.3/` 的 Canonical Schema Registry，不复制第二套 Schema；
- 显式 `FormatChecker` 与 RFC 3339 `date-time` Fail-Closed 自检；
- 三个纯合成 Examples 和 subprocess Runtime Tests。

## Preserved（保持）

- v0.3 Schema 没有重新定义；
- 当前主线的 v0.2、v0.2.1 和 v0.3 Conformance / Compatibility 测试与 Fixtures 保持；
- 所有 Candidate 能力默认关闭，治理、授权和激活效果为 `none`；
- Candidate Contract / Consumer Model evidence only. Not a Runtime Guarantee.

## Security and Privacy（安全与隐私）

Runtime 只读输入，不联网、不执行外部命令、不写回、不访问账号。Schema 错误使用最少必要消息，不回显完整 Payload。Examples 和 Tests 不包含真实身份、账号、设备、路径、凭据或历史私人资料。

## Not Included（不包含）

- Memory Store、Database、Search、Retrieval、Embedding 或 Vector Database；
- AI Provider、LLM、Agent Runtime 或外部执行；
- UI、Web Server、Daemon 或 Background Service；
- Wheel 中的 Schema 复制、Personal Instance 自动接入、自动 Adoption 或 Activation。
