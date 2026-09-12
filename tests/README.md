# Test Registry（测试注册表）

本目录只包含 XINGSHU-Core v0.2 / v0.2.1 / v0.3 / v0.4 Candidate 的可移植测试和 Synthetic Fixtures（合成测试夹具）。不使用真实账号、设备、路径、用户资料、聊天、项目或 Evidence Payload。

## Entrypoints（入口）

- `conformance/v0.2/test_state_separation.py`：State Separation Schema 与转换语义。
- `conformance/v0.2.1/test_state_separation.py`：State Separation v0.2.1 的 Execute Assessment 关联、条件授权与 Runtime Readback Verification（运行回读验证）语义。
- `conformance/v0.2/test_evidence_lifecycle.py`：Scope、Freshness、Correction 与 Payload Exclusion。
- `conformance/v0.2/test_evidence_scope_freshness.py`：严格 RFC 3339 `date-time`、Evidence Scope / Freshness、Review Trigger 与自由文本 Constraint 的 Fail-Closed 语义。
- `conformance/v0.2/test_evidence_proportional_adoption.py`：Class 1/2/3、保守降级与 non-effect。
- `conformance/v0.2/test_pre_execution_assessment.py`：Action / Assessment / Execution / Verification、Stop 与 Idempotency。
- `compatibility/v0.1-v0.2/test_compatibility.py`：v0.1 ↔ v0.2、默认关闭、Personal Isolation 与 Rollback Harness。
- `compatibility/v0.2-v0.2.1/test_compatibility.py`：v0.2 与 v0.2.1 Schema Identity、候选修订撤回以及 No-Downgrade（禁止降级解释）。
- `compatibility/v0.2-v0.3/test_non_interference.py`：受限 Consumer 对禁用 v0.3 Candidate 的 Non-Interference（非干扰）、Unsupported Request Fail-Closed 与 No-Reverse-Migration（禁止反向迁移）。
- `conformance/v0.3/test_memory_entry.py`：来源门禁、晋升审查、证据过期、推断与历史静默。
- `conformance/v0.3/test_knowledge_object.py`：唯一主入口、附录边界、派生视图与跨平台 Scope。
- `conformance/v0.3/test_migration_provenance.py`：来源映射、遗漏原因、源保护，以及 `migrated != verified`。
- `runtime/test_strict_validation.py`：生产严格验证工厂、RFC 3339 `date-time` 和失效依赖时的 Fail-Closed。
- `runtime/test_schema_registry.py`：Canonical Schema Root、记录类型、缺失文件和路径逃逸门禁。
- `runtime/test_validator.py`：只读 Schema / Semantic Validation、隐私边界和稳定决定。
- `runtime/test_cli.py`：`doctor` / `validate` 命令、JSON 输出和 `0 / 2 / 3 / 4` 退出码。

v0.3 Fixtures 全部使用合成标识，覆盖缺少来源、推断未审查、陈旧证据、历史误加载、附录竞争正式来源、派生视图反写、跨平台路径复用、迁移漏源以及迁移完成但运行未验证等 Fail-Closed（失败关闭）路径。

Knowledge Object 与 Migration Provenance 的 Package C Hardening（加固）优先使用 Parameterized Mutation Tests（参数化变异测试），验证角色、不变量、历史加载、来源清单、冲突、遗漏和状态维度独立性；未为覆盖率数量新增重复 Fixture。

v0.2.1 Fixtures 同样只使用合成标识；G1 测试通过 `assessment_ref → action_ref → authorization_requirement` 关联验证 Conditional Authorization（条件授权），G2 测试明确区分 Runtime State / Readback Verification 与业务 Outcome Verification（结果验证）。

## Strict Validation Support（严格验证支持）

- 根目录 `requirements-test.txt` 声明可移植测试依赖；
- `support/strict_schema_validation.py` 为 Draft 2020-12 Schema 显式启用 `FormatChecker`，并在 RFC 3339 `date-time` Checker 不可用或无效时拒绝创建 Validator；
- `support/evidence_scope_freshness.py` 只对调用者提供的已解析对象执行纯函数式 Scope / Freshness 检查，不访问网络、Runtime、数据库或 Personal Instance，也不解释自由文本约束。

标准执行、工具版本、失败注入、可重复性和 Evidence Output Contract 由对应 Candidate Gate 规格控制；本注册表不降低该规格。

## Context Bridge Candidate（上下文桥候选）

本节补充 Context Bridge 候选验证合同的测试登记，提供可移植验证证据。以下路径均相对于 `tests/` 目录；原有版本的测试入口及含义保持不变。

### 测试入口与覆盖范围

- `conformance/context-bridge/test_contract_schemas.py`：覆盖 11 个 Candidate Schema（候选结构定义）及其 16 条内部路由，以四个最小 Positive JSON Seeds（正向 JSON 结构种子）构造合成对象并执行严格结构验证。结构有效不证明 Human Authorization（人类授权）、Source Observation（来源观察）或 Runtime Activation（运行时激活）。
- `runtime/test_context_bridge_validation.py`：覆盖 P2B 的单对象、登记和状态转换合同，包括人类授权边界、登记链一致性及跨证据关联；通过只表示所供声明自洽，不代表真实身份认证或运行时激活。
- `runtime/test_source_adapter_validation.py`：覆盖 P2C Source Adapter（来源适配器）的单对象与交换合同，包括 Opaque Locator（不透明定位符）的精确比较、精确 UTF-8 字节、Fingerprint（指纹）、Provenance（来源追溯信息）和限额；不执行真实来源的输入输出操作。
- `runtime/test_authority_validation.py`：覆盖 P2D 对调用方提供的 Authority Context（权限上下文）的验证，包括对象原始字节与指纹，以及客户端、引用、绑定、操作和时间约束；PASS（通过）不认证真实调用者、会话或 Control Plane（控制平面）。
- `runtime/test_resolve_context_validation.py`：覆盖 P2E Resolve（上下文解析）的交换合同，包括委托权限验证、直接来源证据要求、Freshness（新鲜度）、来源追溯信息、Payload（正文载荷）、聚合指纹及错误证据模式；通过不代表真实来源已读取或运行时已激活。错误交换通过仅表示错误声明有据，不代表解析成功或应重试。
- `runtime/test_schema_registry.py`：在原有注册表测试上补充旧版 `discover()` 精确保留 3 条路由、Context Bridge 内部路由共 16 条且对应 11 个唯一候选 Schema，以及 `resolve_context_error` 的内部支持边界。
- `runtime/test_validator.py`：在原有通用验证测试上补充 18 条公开路由（3 条旧版与 15 条候选）、专用验证器结果及各自诊断原样保留、`derived_provider_metadata` 仅做 Schema 验证的通用分支，以及通用单对象验证不执行 Cross-evidence APIs（跨证据接口）。同时固定候选原始 JSON 根级重复判别字段的拒绝行为和旧版重复 `record_type` 的末值生效行为。
- `runtime/test_cli.py`：在原有 CLI（命令行接口）测试上补充 15 条公开候选路由、专用诊断原样保留和内部路由拒绝。`resolve_context_error` 不是公开 CLI 验证类型；CLI PASS 仅表示对应单对象验证通过。
- `compatibility/context-bridge/test_non_interference.py`：验证 Context Bridge 路由不改变旧版注册表、验证器和 CLI 行为，内部路由知晓不会自动造成公开暴露。显式候选验证不产生运行时激活或治理效力；这些证据不构成反向迁移或自动采用声明。

### 内部路由与公开入口

Schema Registry（结构注册表）包含 **16 条内部候选路由**，通用验证器包含 **15 条公开候选路由**。差额来自 `resolve_context_error`：它是内部支持路由，可由注册表解析，但不是通用公开验证路由，也不是公开 CLI 的 `--type` 选项。文件自身声明该类型时，通用验证返回 `candidate_unsupported_route`；显式使用 `--type resolve_context_error` 则属于命令行用法错误，退出码为 `4`。

### 合成种子与构造支持

`support/context_bridge_fixtures.py` 是 Test-only Synthetic Construction Support（仅用于测试的合成构造支持），用于显式构造确定性的关联对象、Python 原生 `bytes`（字节）、测试指纹和固定时间戳。它不判断合同是否有效，不自动修复关联，也不是生产序列化器、规范序列化协议或运行时适配器。

四个正向结构种子为：

- `fixtures/context-bridge/context-candidate-valid.json`：合成候选对象。
- `fixtures/context-bridge/source-adapter-manifest-valid.json`：合成来源适配器合同声明。
- `fixtures/context-bridge/trusted-client-profile-valid.json`：合成客户端档案声明。
- `fixtures/context-bridge/derived-provider-metadata-valid.json`：合成派生元数据声明。

这些 JSON 文件仅是正向结构种子，不是完整登记链、真实服务提供方配置、真实可信客户端、真实用户数据或真实授权证据。

### 隐私、可移植性与判定边界

P3 测试保持 Portable（可移植）、Synthetic（合成）和 Deterministic（确定性）：不访问真实服务提供方、网络、真实文件来源、账号、设备、Personal Instance（私人实例）或用户私密资料。测试可以读取仓库内的合成夹具与 Schema，并使用 `tempfile`（临时文件）验证输入行为；这不属于真实来源访问。

以下区分说明既有测试的证据边界，不新增生产规则：

| 测试判定或对象 | 不能据此证明 |
|---|---|
| Schema 有效 | 已获人类授权 |
| 单对象有效 | 登记已完成 |
| Source Adapter 交换有效 | 真实外部来源存在 |
| 权限上下文符合条件 | 调用者已经身份认证 |
| Resolve 交换有效 | 生产运行时已激活 |
| 通用 CLI PASS | 跨证据验证已完成 |
| Derived Metadata（派生元数据） | 具有最终权威性 |
