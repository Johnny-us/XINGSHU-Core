# Test Registry（测试注册表）

本目录只包含 XINGSHU-Core v0.2 / v0.2.1 / v0.3 Candidate 的可移植测试和 Synthetic Fixtures（合成测试夹具）。不使用真实账号、设备、路径、用户资料、聊天、项目或 Evidence Payload。

## Entrypoints（入口）

- `conformance/v0.2/test_state_separation.py`：State Separation Schema 与转换语义。
- `conformance/v0.2.1/test_state_separation.py`：State Separation v0.2.1 的 Execute Assessment 关联、条件授权与 Runtime Readback Verification（运行回读验证）语义。
- `conformance/v0.2/test_evidence_lifecycle.py`：Scope、Freshness、Correction 与 Payload Exclusion。
- `conformance/v0.2/test_evidence_scope_freshness.py`：严格 RFC 3339 `date-time`、Evidence Scope / Freshness、Review Trigger 与自由文本 Constraint 的 Fail-Closed 语义。
- `conformance/v0.2/test_evidence_proportional_adoption.py`：Class 1/2/3、保守降级与 non-effect。
- `conformance/v0.2/test_pre_execution_assessment.py`：Action / Assessment / Execution / Verification、Stop 与 Idempotency。
- `compatibility/v0.1-v0.2/test_compatibility.py`：v0.1 ↔ v0.2、默认关闭、Personal Isolation 与 Rollback Harness。
- `compatibility/v0.2-v0.2.1/test_compatibility.py`：v0.2 与 v0.2.1 Schema Identity、候选修订撤回以及 No-Downgrade（禁止降级解释）。
- `conformance/v0.3/test_memory_entry.py`：来源门禁、晋升审查、证据过期、推断与历史静默。
- `conformance/v0.3/test_knowledge_object.py`：唯一主入口、附录边界、派生视图与跨平台 Scope。
- `conformance/v0.3/test_migration_provenance.py`：来源映射、遗漏原因、源保护，以及 `migrated != verified`。

v0.3 Fixtures 全部使用合成标识，覆盖缺少来源、推断未审查、陈旧证据、历史误加载、附录竞争正式来源、派生视图反写、跨平台路径复用、迁移漏源以及迁移完成但运行未验证等 Fail-Closed（失败关闭）路径。

v0.2.1 Fixtures 同样只使用合成标识；G1 测试通过 `assessment_ref → action_ref → authorization_requirement` 关联验证 Conditional Authorization（条件授权），G2 测试明确区分 Runtime State / Readback Verification 与业务 Outcome Verification（结果验证）。

## Strict Validation Support（严格验证支持）

- 根目录 `requirements-test.txt` 声明可移植测试依赖；
- `support/strict_schema_validation.py` 为 Draft 2020-12 Schema 显式启用 `FormatChecker`，并在 RFC 3339 `date-time` Checker 不可用或无效时拒绝创建 Validator；
- `support/evidence_scope_freshness.py` 只对调用者提供的已解析对象执行纯函数式 Scope / Freshness 检查，不访问网络、Runtime、数据库或 Personal Instance，也不解释自由文本约束。

标准执行、工具版本、失败注入、可重复性和 Evidence Output Contract 由对应 Candidate Gate 规格控制；本注册表不降低该规格。
