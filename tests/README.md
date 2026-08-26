# Test Registry（测试注册表）

本目录只包含 XINGSHU-Core v0.2 / v0.3 / v0.4 Candidate 的可移植测试和 Synthetic Fixtures（合成测试夹具）。不使用真实账号、设备、路径、用户资料、聊天、项目或 Evidence Payload。

## Entrypoints（入口）

- `conformance/v0.2/test_state_separation.py`：State Separation Schema 与转换语义。
- `conformance/v0.2/test_evidence_lifecycle.py`：Scope、Freshness、Correction 与 Payload Exclusion。
- `conformance/v0.2/test_evidence_proportional_adoption.py`：Class 1/2/3、保守降级与 non-effect。
- `conformance/v0.2/test_pre_execution_assessment.py`：Action / Assessment / Execution / Verification、Stop 与 Idempotency。
- `compatibility/v0.1-v0.2/test_compatibility.py`：v0.1 ↔ v0.2、默认关闭、Personal Isolation 与 Rollback Harness。
- `conformance/v0.3/test_memory_entry.py`：来源门禁、晋升审查、证据过期、推断与历史静默。
- `conformance/v0.3/test_knowledge_object.py`：唯一主入口、附录边界、派生视图与跨平台 Scope。
- `conformance/v0.3/test_migration_provenance.py`：来源映射、遗漏原因、源保护，以及 `migrated != verified`。
- `runtime/test_validator.py`：统一 Result、Decision、语义判断、只读和安全错误输出。
- `runtime/test_schema_registry.py`：Canonical Schema（唯一 Schema）发现、环境覆盖与失败关闭。
- `runtime/test_cli.py`：通过 subprocess 实际运行 Version、Doctor、Validate、JSON 输出与退出码。

v0.3 Fixtures 与 v0.4 Examples 全部使用合成标识，覆盖缺少来源、推断未审查、陈旧证据、历史误加载、附录竞争正式来源、派生视图反写、跨平台路径复用、迁移漏源以及迁移完成但运行未验证等 Fail-Closed（失败关闭）路径。

标准执行、工具版本、失败注入、可重复性和 Evidence Output Contract 由对应 Candidate Gate 规格控制；本注册表不降低该规格。
