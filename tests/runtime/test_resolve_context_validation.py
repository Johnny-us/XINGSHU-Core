"""P2E 合成证据回归；正向 PASS 不证明真实 Source 读取或身份认证。

错误交换 PASS 只证明错误声明有据，不代表解析成功、应重试或运行时激活。
resolve_context_error 是内部支持路由；本文件不测试公开 CLI（命令行接口）。
"""

import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from xingshu_core import authority_validation as authority
from xingshu_core import resolve_context_validation as resolve
from xingshu_core import source_adapter_validation as source
from xingshu_core.decisions import Decision
from xingshu_core.schema_registry import SchemaRegistry

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/support"))
import context_bridge_fixtures as fixtures  # noqa: E402

SCHEMA_REF = "schemas/candidate/context-bridge/resolve-context.schema.json"
SENTINELS = (
    "SYNTHETIC_P3_PRIVATE_TEXT_SENTINEL",
    "SYNTHETIC_P3_PRIVATE_LOCATOR_SENTINEL",
    "SYNTHETIC_P3_PRIVATE_ID_SENTINEL",
)
# 固定二入口向量：b"Alpha\n" 与 UTF-8 的 "乙\n"（6 和 4 bytes）。
# 实现阶段独立对固定分帧字节计算一次的期望值；不定义新公共序列化协议。
TWO_ENTRY_FINGERPRINT = "sha256:777cc7965c52de36cebce3e582ae121e56f5b5e51f5b9cc0548b6ab6bc48558a"


def bind_authority_objects(context):
    """显式重绑已知三对象的字节，不判断准入或修复业务字段。"""
    profile_bytes = fixtures.encode_test_object(context["client_profile"])
    reference_bytes = fixtures.encode_test_object(context["reference"])
    binding = context["runtime_binding"]
    binding["trusted_client_profile_fingerprint"] = fixtures.fingerprint(profile_bytes)
    binding["reference_fingerprint"] = fixtures.fingerprint(reference_bytes)
    binding_bytes = fixtures.encode_test_object(binding)
    context["authority_context"]["object_bytes"] = {
        "trusted_client_profile": profile_bytes, "registered_context_reference": reference_bytes,
        "runtime_binding": binding_bytes,
    }
    context["authority_context"]["control_plane_selection"]["binding_fingerprint"] = fixtures.fingerprint(binding_bytes)


def resolve_sample():
    """单入口正向样本；所有 Source 定位符只是不透明合成字符串。"""
    reference = fixtures.build_registered_context_reference({
        "authorization_id": fixtures.synthetic_id("authorization"),
        "context_type": "document", "source_id": fixtures.synthetic_id("source"),
        "final_canonical_name": "Synthetic P3 document",
        "final_source_locator": "synthetic:root:alpha",
        "final_source_entry_points": [fixtures.SYNTHETIC_ENTRY, "synthetic:entry:beta"],
        "final_access_scope": "private", "final_allowed_clients": [fixtures.SYNTHETIC_CLIENT_ID],
        "final_freshness_policy": "verify_before_use",
        "final_provenance_policy": "locator_and_verification",
        "retrieval_hint": "Synthetic P3 bounded hint", "initial_status": "active",
    })
    profile = fixtures.load_trusted_client_profile_seed()
    reference_bytes, profile_bytes = fixtures.encode_test_object(reference), fixtures.encode_test_object(profile)
    binding = fixtures.build_runtime_binding(profile, reference, profile_bytes=profile_bytes, reference_bytes=reference_bytes)
    binding_bytes = fixtures.encode_test_object(binding)
    auth = {
        "object_bytes": {"trusted_client_profile": profile_bytes,
                         "registered_context_reference": reference_bytes, "runtime_binding": binding_bytes},
        "control_plane_selection": {
            "client_id": profile["client_id"], "binding_fingerprint": fixtures.fingerprint(binding_bytes),
            "transport_binding_id": binding["transport_binding_id"], "transport_class": binding["transport_class"],
        },
        "operation": "resolve_context", "evaluated_at": fixtures.utc_timestamp(6),
    }
    manifest = fixtures.load_source_adapter_manifest_seed()
    source_request = fixtures.build_source_adapter_request(manifest)
    source_response = fixtures.build_source_adapter_result(source_request, text="Alpha\n")
    source_response["provenance"]["observed_at"] = fixtures.utc_timestamp(7)
    request = fixtures.build_resolve_context_request(reference)
    request["entry_selection"] = [fixtures.SYNTHETIC_ENTRY]
    response = fixtures.build_resolve_context_result(
        request, reference, binding, source_response, reference_bytes=reference_bytes, exact_content_bytes=b"Alpha\n",
    )
    response["freshness"]["verified_at"] = fixtures.utc_timestamp(8)
    context = {
        "reference": reference, "client_profile": profile, "runtime_binding": binding,
        "authority_context": auth, "resolved_at": fixtures.utc_timestamp(8),
        "resolution_event": {
            "observation_id": source_response["provenance"]["observation_id"],
            "verification_evidence_id": response["freshness"]["verification_evidence_id"],
            "observed_at": fixtures.utc_timestamp(7), "verified_at": fixtures.utc_timestamp(8),
        },
        "source_exchanges": [{
            "manifest": manifest, "request": source_request, "response": source_response,
            "expected_scope_id": source_request["scope_id"], "exact_content_bytes": b"Alpha\n",
        }],
    }
    return dict(request=request, response=response, resolution_context=context)


def two_entry_sample():
    """只组装固定二入口向量，不计算聚合指纹或预期判定。"""
    sample = resolve_sample()
    request, response, context = sample["request"], sample["response"], sample["resolution_context"]
    request["entry_selection"] = [fixtures.SYNTHETIC_ENTRY, "synthetic:entry:beta"]
    request["requested_limits"]["max_items"] = 2
    second = copy.deepcopy(context["source_exchanges"][0])
    second["request"].update(request_id=fixtures.synthetic_id("source-request", 2), target_locator="synthetic:entry:beta")
    second["response"] = fixtures.build_source_adapter_result(second["request"], text="乙\n")
    second["response"]["provenance"]["observed_at"] = fixtures.utc_timestamp(7)
    second["response"]["provenance"]["observation_id"] = fixtures.synthetic_id("observation", 2)
    second["exact_content_bytes"] = b"\xe4\xb9\x99\n"
    context["source_exchanges"].append(second)
    second_result = fixtures.build_resolve_context_result(
        request, context["reference"], context["runtime_binding"], second["response"],
        reference_bytes=context["authority_context"]["object_bytes"]["registered_context_reference"],
        exact_content_bytes=second["exact_content_bytes"],
    )
    response["payload"].append(second_result["payload"][0])
    response["applied_limits"].update(max_items=2, returned_items=2, returned_bytes=10)
    response["provenance"].update(entry_points=[fixtures.SYNTHETIC_ENTRY, "synthetic:entry:beta"], content_fingerprint=TWO_ENTRY_FINGERPRINT)
    return sample


def authority_error_sample(code):
    """仅换成明确的错误信封和无正文证据上下文；调用方提供错误原因。"""
    sample = resolve_sample()
    sample["response"] = fixtures.build_resolve_context_error(sample["request"])
    sample["response"].update(error_code=code, observed_at=fixtures.utc_timestamp(7))
    del sample["resolution_context"]["resolution_event"]
    del sample["resolution_context"]["source_exchanges"]
    return sample


def source_error_sample(code):
    sample = authority_error_sample(code)
    manifest = fixtures.load_source_adapter_manifest_seed()
    request = fixtures.build_source_adapter_request(manifest)
    response = fixtures.build_source_adapter_error(request)
    response.update(error_code=code, observed_at=fixtures.utc_timestamp(7))
    sample["resolution_context"]["source_exchanges"] = [{
        "manifest": manifest, "request": request, "response": response, "expected_scope_id": request["scope_id"],
    }]
    return sample


class ResolveContextValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = SchemaRegistry()

    def setUp(self):
        self.sample = resolve_sample()

    def check(self, sample=None):
        return resolve.validate_resolve_context_exchange(
            **(self.sample if sample is None else sample), registry=self.registry,
        )

    def assert_positive(self, result, route="resolve_context_result", status="resolve_exchange_valid"):
        self.assertEqual(Decision.PASS, result.decision)
        self.assertEqual(status, result.status)
        self.assertEqual(route, result.record_type)
        self.assertEqual("context-bridge-candidate", result.schema_version)
        self.assertEqual(SCHEMA_REF, result.schema_ref)
        self.assertEqual((), result.errors)

    def assert_failure(self, result, code, path=None, decision=Decision.REJECT, status="rejected"):
        self.assertEqual(decision, result.decision)
        self.assertEqual(status, result.status)
        self.assertIn(code, {issue.code for issue in result.errors})
        if path is not None:
            self.assertIn((code, path), {(issue.code, issue.path) for issue in result.errors})
        rendered = str(result) + json.dumps(result.to_dict(), ensure_ascii=False)
        for sentinel in SENTINELS:
            self.assertNotIn(sentinel, rendered)

    def test_three_single_objects_have_exact_metadata_and_are_immutable(self):
        records = (self.sample["request"], self.sample["response"], fixtures.build_resolve_context_error(self.sample["request"]))
        for record in records:
            with self.subTest(route=record["object_kind"]):
                before = copy.deepcopy(record)
                self.assert_positive(resolve.validate_resolve_context_object(record, record["object_kind"], self.registry), record["object_kind"], "object_valid")
                self.assertEqual(before, record)

    def test_single_object_route_and_schema_failures(self):
        result = resolve.validate_resolve_context_object(self.sample["request"], SENTINELS[2], self.registry)
        self.assert_failure(result, "resolve_unsupported_route", "$")
        self.assertIsNone(result.record_type)
        self.assertIsNone(result.schema_ref)
        wrong = copy.deepcopy(self.sample["request"])
        wrong["object_kind"] = "synthetic_wrong_route"
        self.assert_failure(resolve.validate_resolve_context_object(wrong, "resolve_context_request", self.registry), "resolve_route_mismatch", "$")
        for record in (self.sample["request"], self.sample["response"], fixtures.build_resolve_context_error(self.sample["request"])):
            with self.subTest(route=record["object_kind"]):
                record = copy.deepcopy(record)
                record[SENTINELS[1]] = SENTINELS[0]
                self.assert_failure(resolve.validate_resolve_context_object(record, record["object_kind"], self.registry), "resolve_schema_invalid", "$")

    def test_invalid_non_json_and_cyclic_objects(self):
        invalid = copy.deepcopy(self.sample["request"])
        invalid["query_hint"] = b"Synthetic non-JSON value"
        cyclic = copy.deepcopy(self.sample["request"])
        cyclic["requested_limits"] = cyclic
        for record in (None, [], SENTINELS[0], invalid, cyclic):
            with self.subTest(kind=type(record).__name__):
                self.assert_failure(resolve.validate_resolve_context_object(record, "resolve_context_request", self.registry), "resolve_invalid_object")

    def test_single_object_registry_and_strict_unavailability(self):
        with patch.object(resolve, "SchemaRegistry", side_effect=RuntimeError(SENTINELS[0])):
            self.assert_failure(resolve.validate_resolve_context_object(self.sample["request"], "resolve_context_request"), "resolve_validation_unavailable", decision=Decision.ERROR, status="validation_unavailable")
        validator = self.registry.validator_for("resolve_context_request")
        with patch.object(type(validator), "iter_errors", side_effect=RuntimeError(SENTINELS[0])):
            self.assert_failure(resolve.validate_resolve_context_object(self.sample["request"], "resolve_context_request", self.registry), "resolve_validation_unavailable", decision=Decision.ERROR, status="validation_unavailable")

    def test_positive_direct_source_evidence_and_all_inputs_immutable(self):
        before = copy.deepcopy(self.sample)
        context = self.sample["resolution_context"]
        self.assertEqual("resolve_context", context["authority_context"]["operation"])
        self.assertIs(type(context["source_exchanges"][0]["exact_content_bytes"]), bytes)
        self.assert_positive(self.check())
        self.assertEqual(before, self.sample)

    def test_direct_source_evidence_is_required(self):
        for value in (None, []):
            with self.subTest(evidence=value):
                sample = copy.deepcopy(self.sample)
                if value is None:
                    del sample["resolution_context"]["source_exchanges"]
                else:
                    sample["resolution_context"]["source_exchanges"] = value
                self.assert_failure(self.check(sample), "resolve_context_missing", "$/resolution_context/source_exchanges", Decision.NEEDS_REVIEW, "incomplete_resolution_context")
        # 当前封闭 context 没有 Derived API；未知字段拒绝不代表新增业务语义。
        sample = copy.deepcopy(self.sample)
        del sample["resolution_context"]["source_exchanges"]
        sample["resolution_context"]["synthetic_derived_cache"] = fixtures.load_derived_provider_metadata_seed()
        self.assert_failure(self.check(sample), "resolve_invalid_object", "$/resolution_context")

    def test_missing_resolution_context_fields(self):
        for field in ("reference", "client_profile", "runtime_binding", "authority_context", "resolved_at", "resolution_event"):
            with self.subTest(field=field):
                sample = copy.deepcopy(self.sample)
                del sample["resolution_context"][field]
                self.assert_failure(self.check(sample), "resolve_context_missing", decision=Decision.NEEDS_REVIEW, status="incomplete_resolution_context")

    def test_authority_delegation_pass_reject_and_needs_review(self):
        for case, expected in (("eligible", Decision.PASS), ("paused", Decision.REJECT), ("missing_bytes", Decision.NEEDS_REVIEW)):
            with self.subTest(case=case):
                sample = copy.deepcopy(self.sample)
                context = sample["resolution_context"]
                if case == "paused":
                    context["reference"]["status"] = "paused"
                    bind_authority_objects(context)
                    sample["response"]["reference_fingerprint"] = context["runtime_binding"]["reference_fingerprint"]
                elif case == "missing_bytes":
                    del context["authority_context"]["object_bytes"]["trusted_client_profile"]
                observed = []
                def delegated(*args, **kwargs):
                    result = authority.validate_reference_authority(*args, **kwargs)
                    observed.append(result)
                    return result
                with patch.object(resolve, "validate_reference_authority", side_effect=delegated):
                    result = self.check(sample)
                self.assertEqual([expected], [item.decision for item in observed])
                if case == "eligible":
                    self.assert_positive(result)
                elif case == "paused":
                    self.assert_failure(result, "resolve_authority_not_eligible")
                    self.assertIn("authority_reference_not_active", {i.code for i in observed[0].errors})
                else:
                    self.assert_failure(result, "resolve_context_missing", decision=Decision.NEEDS_REVIEW, status="incomplete_resolution_context")

    def test_authority_delegation_real_registry_error(self):
        observed = []
        def delegated(*args, **kwargs):
            # 模拟 P2E 已接纳对象后，P2D 实际使用的严格验证器失效。
            with patch.object(self.registry, "validator_for", side_effect=RuntimeError(SENTINELS[0])):
                result = authority.validate_reference_authority(*args, **kwargs)
            observed.append(result)
            return result
        with patch.object(resolve, "validate_reference_authority", side_effect=delegated):
            result = self.check()
        self.assertEqual([Decision.ERROR], [item.decision for item in observed])
        self.assertIn("authority_validation_unavailable", {i.code for i in observed[0].errors})
        self.assert_failure(result, "resolve_validation_unavailable", decision=Decision.ERROR, status="validation_unavailable")

    def test_resolution_requires_the_resolve_operation(self):
        context = self.sample["resolution_context"]
        context["authority_context"]["operation"] = "get_reference"
        # 该操作在 P2D 自身可 eligible，但不是 P2E 所需的 resolve_context。
        result = authority.validate_reference_authority(
            context["reference"], context["client_profile"], context["runtime_binding"],
            authority_context=context["authority_context"], registry=self.registry,
        )
        self.assertEqual((Decision.PASS, "authority_context_eligible"), (result.decision, result.status))
        self.assert_failure(self.check(), "resolve_authority_not_eligible", "$/resolution_context/authority_context")

    def test_source_delegation_pass_reject_and_needs_review(self):
        for case, expected in (("valid", Decision.PASS), ("wrong_bytes", Decision.REJECT), ("missing_manifest", Decision.NEEDS_REVIEW)):
            with self.subTest(case=case):
                sample = copy.deepcopy(self.sample)
                exchange = sample["resolution_context"]["source_exchanges"][0]
                if case == "wrong_bytes":
                    exchange["exact_content_bytes"] = b"Other\n"
                elif case == "missing_manifest":
                    del exchange["manifest"]
                observed = []
                def delegated(*args, **kwargs):
                    result = source.validate_source_adapter_exchange(*args, **kwargs)
                    observed.append(result)
                    return result
                with patch.object(resolve, "validate_source_adapter_exchange", side_effect=delegated):
                    result = self.check(sample)
                self.assertEqual([expected], [item.decision for item in observed])
                if case == "valid":
                    self.assert_positive(result)
                elif case == "wrong_bytes":
                    self.assert_failure(result, "resolve_source_observation_mismatch")
                    self.assertIn("source_adapter_exact_bytes_mismatch", {i.code for i in observed[0].errors})
                else:
                    self.assert_failure(result, "resolve_context_missing", decision=Decision.NEEDS_REVIEW, status="incomplete_resolution_context")

    def test_source_delegation_real_registry_error(self):
        observed = []
        def delegated(*args, **kwargs):
            # 在真实委托调用中触发 P2C 自己的 ERROR 分支，不伪造 ValidationResult。
            with patch.object(self.registry, "validator_for", side_effect=RuntimeError(SENTINELS[0])):
                result = source.validate_source_adapter_exchange(*args, **kwargs)
            observed.append(result)
            return result
        with patch.object(resolve, "validate_source_adapter_exchange", side_effect=delegated):
            result = self.check()
        self.assertEqual([Decision.ERROR], [item.decision for item in observed])
        self.assertIn("source_adapter_validation_unavailable", {i.code for i in observed[0].errors})
        self.assert_failure(result, "resolve_validation_unavailable", decision=Decision.ERROR, status="validation_unavailable")

    def test_request_reference_and_binding_linkage(self):
        for section, field, value, code, path in (
            ("request", "reference_id", SENTINELS[2], "resolve_reference_mismatch", "$/request/reference_id"),
            ("response", "request_id", SENTINELS[2], "resolve_request_linkage_mismatch", "$/response/request_id"),
            ("response", "reference_id", SENTINELS[2], "resolve_request_linkage_mismatch", "$/response/reference_id"),
            ("response", "reference_id", SENTINELS[2], "resolve_reference_mismatch", "$/response/reference_id"),
            ("response", "binding_id", SENTINELS[2], "resolve_binding_mismatch", "$/response/binding_id"),
            ("response", "reference_fingerprint", fixtures.fingerprint(b"Synthetic other reference"), "resolve_reference_mismatch", "$/response/reference_fingerprint"),
        ):
            with self.subTest(section=section, field=field, code=code):
                sample = copy.deepcopy(self.sample)
                sample[section][field] = value
                self.assert_failure(self.check(sample), code, path)

    def test_narrowed_selection_and_optional_selection(self):
        self.assert_positive(self.check())
        del self.sample["request"]["entry_selection"]
        self.assert_positive(self.check())
        context = self.sample["resolution_context"]
        context["runtime_binding"]["bound_entry_points"] = [fixtures.SYNTHETIC_ENTRY]
        bind_authority_objects(context)
        self.assert_positive(self.check())

    def test_entry_selection_cannot_reorder_or_expand(self):
        for entries in (["synthetic:entry:beta", fixtures.SYNTHETIC_ENTRY], ["synthetic:entry:unknown"]):
            with self.subTest(entries=entries):
                sample = two_entry_sample()
                sample["request"]["entry_selection"] = entries
                self.assert_failure(self.check(sample), "resolve_entry_selection_mismatch", "$/request/entry_selection")
        sample = two_entry_sample()
        sample["response"]["provenance"]["entry_points"].reverse()
        self.assert_failure(self.check(sample), "resolve_entry_selection_mismatch", "$/response/provenance")
        self.sample["response"]["payload"][0]["entry_point"] = "synthetic:entry:beta"
        self.assert_failure(self.check(), "resolve_payload_mismatch", "$/response/payload")

    def test_source_scope_source_id_and_locator_linkage(self):
        for field in ("expected_scope_id", "source_id", "target_locator"):
            with self.subTest(field=field):
                sample = copy.deepcopy(self.sample)
                exchange = sample["resolution_context"]["source_exchanges"][0]
                if field == "expected_scope_id":
                    exchange[field] = fixtures.synthetic_id("other-scope")
                else:
                    exchange["request"][field] = "synthetic:entry:beta" if field == "target_locator" else fixtures.synthetic_id("other-source")
                    exchange["response"] = fixtures.build_source_adapter_result(exchange["request"], text="Alpha\n")
                    exchange["response"]["provenance"]["observed_at"] = fixtures.utc_timestamp(7)
                code = "resolve_entry_selection_mismatch" if field == "target_locator" else "resolve_source_observation_mismatch"
                self.assert_failure(self.check(sample), code)

    def test_resolve_counts_and_limit_relations(self):
        for field, value in (("returned_items", 2), ("returned_bytes", 7), ("max_bytes", 5), ("max_items", 2), ("max_bytes", 1025)):
            with self.subTest(field=field, value=value):
                sample = copy.deepcopy(self.sample)
                sample["response"]["applied_limits"][field] = value
                self.assert_failure(self.check(sample), "resolve_limit_mismatch", "$/response/applied_limits")
        sample = two_entry_sample()
        sample["response"]["applied_limits"]["max_items"] = 1
        self.assert_failure(self.check(sample), "resolve_limit_mismatch")
        for field, value in (("max_items", 1), ("max_bytes", 5)):
            with self.subTest(request_limit=field):
                sample = two_entry_sample()
                sample["request"]["requested_limits"][field] = value
                self.assert_failure(self.check(sample), "resolve_limit_mismatch")

    def test_payload_fields_match_direct_read_evidence(self):
        for field, value, code in (
            ("text", SENTINELS[0], "resolve_payload_mismatch"),
            ("content_type", "text/markdown", "resolve_payload_mismatch"),
            ("byte_count", 7, "resolve_payload_mismatch"),
            ("content_fingerprint", fixtures.fingerprint(b"Synthetic changed text"), "resolve_payload_fingerprint_mismatch"),
        ):
            with self.subTest(field=field):
                sample = copy.deepcopy(self.sample)
                sample["response"]["payload"][0][field] = value
                self.assert_failure(self.check(sample), code, "$/response/payload")
        # encoding 的冻结 Schema 是 const utf-8，失配在结构门禁先被拒绝。
        self.sample["response"]["payload"][0]["encoding"] = "synthetic_other_encoding"
        self.assert_failure(self.check(), "resolve_schema_invalid", "$/response")

    def test_source_exact_bytes_are_native_and_required(self):
        for value in ("Alpha\n", bytearray(b"Alpha\n")):
            with self.subTest(kind=type(value).__name__):
                sample = copy.deepcopy(self.sample)
                sample["resolution_context"]["source_exchanges"][0]["exact_content_bytes"] = value
                self.assert_failure(self.check(sample), "resolve_invalid_object", "$/resolution_context/source_exchanges")
        del self.sample["resolution_context"]["source_exchanges"][0]["exact_content_bytes"]
        self.assert_failure(self.check(), "resolve_context_missing", decision=Decision.NEEDS_REVIEW, status="incomplete_resolution_context")

    def test_freshness_and_provenance_match_explicit_event(self):
        for section, field, value, code in (
            ("freshness", "verified_at", fixtures.utc_timestamp(7), "resolve_freshness_mismatch"),
            ("freshness", "verification_evidence_id", SENTINELS[2], "resolve_freshness_mismatch"),
            ("provenance", "observation_id", SENTINELS[2], "resolve_provenance_mismatch"),
            ("provenance", "observed_at", fixtures.utc_timestamp(6), "resolve_provenance_mismatch"),
            ("provenance", "source_id", SENTINELS[2], "resolve_provenance_mismatch"),
        ):
            with self.subTest(section=section, field=field):
                sample = copy.deepcopy(self.sample)
                sample["response"][section][field] = value
                self.assert_failure(self.check(sample), code, "$/response/" + section)

    def test_explicit_source_event_and_resolution_time_order(self):
        for case in ("observed_after_verified", "verified_after_resolved", "source_before_evaluated", "source_after_event"):
            with self.subTest(case=case):
                sample = copy.deepcopy(self.sample)
                context = sample["resolution_context"]
                if case == "observed_after_verified":
                    context["resolution_event"]["verified_at"] = fixtures.utc_timestamp(6)
                    sample["response"]["freshness"]["verified_at"] = fixtures.utc_timestamp(6)
                elif case == "verified_after_resolved":
                    context["resolved_at"] = fixtures.utc_timestamp(7)
                else:
                    seconds = 5 if case == "source_before_evaluated" else 8
                    context["source_exchanges"][0]["response"]["provenance"]["observed_at"] = fixtures.utc_timestamp(seconds)
                self.assert_failure(self.check(sample), "resolve_timestamp_inconsistent")

    def test_single_entry_fingerprint_is_exact_content_fingerprint(self):
        self.assertEqual(self.sample["response"]["payload"][0]["content_fingerprint"], self.sample["response"]["provenance"]["content_fingerprint"])
        self.assert_positive(self.check())
        self.sample["response"]["provenance"]["content_fingerprint"] = fixtures.fingerprint(b"Synthetic other body")
        self.assert_failure(self.check(), "resolve_provenance_mismatch", "$/response/provenance")

    def test_fixed_two_entry_aggregate_and_evidence_shape(self):
        sample = two_entry_sample()
        before = copy.deepcopy(sample)
        response, exchanges = sample["response"], sample["resolution_context"]["source_exchanges"]
        entries = [item["entry_point"] for item in response["payload"]]
        self.assertEqual(2, len(response["payload"]))
        self.assertEqual(2, len(exchanges))
        self.assertEqual(2, len(set(entries)))
        self.assertEqual(entries, response["provenance"]["entry_points"])
        self.assertEqual(entries, [item["request"]["target_locator"] for item in exchanges])
        self.assertEqual([b"Alpha\n", b"\xe4\xb9\x99\n"], [item["exact_content_bytes"] for item in exchanges])
        self.assertEqual(TWO_ENTRY_FINGERPRINT, response["provenance"]["content_fingerprint"])
        for exchange in exchanges:
            self.assertIs(type(exchange["exact_content_bytes"]), bytes)
            result = source.validate_source_adapter_exchange(exchange["manifest"], exchange["request"], exchange["response"], exact_content_bytes=exchange["exact_content_bytes"], registry=self.registry)
            self.assertEqual((Decision.PASS, "exchange_valid", ()), (result.decision, result.status, result.errors))
        self.assert_positive(self.check(sample))
        self.assertEqual(before, sample)

    def test_changed_content_cannot_reuse_fixed_aggregate(self):
        sample = two_entry_sample()
        context = sample["resolution_context"]
        exchange = context["source_exchanges"][1]
        exchange["response"] = fixtures.build_source_adapter_result(exchange["request"], text="丙\n")
        exchange["response"]["provenance"]["observed_at"] = fixtures.utc_timestamp(7)
        exchange["exact_content_bytes"] = "丙\n".encode("utf-8")
        sample["response"]["payload"][1]["text"] = "丙\n"
        sample["response"]["payload"][1]["content_fingerprint"] = fixtures.fingerprint(exchange["exact_content_bytes"])
        self.assert_failure(self.check(sample), "resolve_provenance_mismatch", "$/response/provenance")

    def test_changed_order_cannot_reuse_fixed_aggregate(self):
        sample = two_entry_sample()
        context = sample["resolution_context"]
        # 整组入口关系显式改成合法反向顺序，仅保留旧聚合指纹作为反例。
        context["reference"]["source_entry_points"].reverse()
        context["runtime_binding"]["bound_entry_points"].reverse()
        bind_authority_objects(context)
        sample["response"]["reference_fingerprint"] = context["runtime_binding"]["reference_fingerprint"]
        sample["request"]["entry_selection"].reverse()
        sample["response"]["payload"].reverse()
        sample["response"]["provenance"]["entry_points"].reverse()
        context["source_exchanges"].reverse()
        result = self.check(sample)
        self.assert_failure(result, "resolve_provenance_mismatch", "$/response/provenance")
        self.assertEqual({"resolve_provenance_mismatch"}, {issue.code for issue in result.errors})

    def test_multi_entry_missing_and_duplicate_evidence_cannot_pass(self):
        sample = two_entry_sample()
        sample["resolution_context"]["source_exchanges"].pop()
        self.assert_failure(self.check(sample), "resolve_context_missing", decision=Decision.NEEDS_REVIEW, status="incomplete_resolution_context")
        sample = two_entry_sample()
        sample["response"]["payload"][1] = copy.deepcopy(sample["response"]["payload"][0])
        sample["response"]["applied_limits"]["returned_bytes"] = 12
        self.assert_failure(self.check(sample), "resolve_context_missing", decision=Decision.NEEDS_REVIEW, status="incomplete_resolution_context")

    def test_supported_authority_error_declarations(self):
        cases = (
            ("client_not_allowed", "reference", "allowed_clients", []),
            ("reference_not_active", "reference", "status", "paused"),
            ("stale_locator", "reference", "status", "stale_locator"),
            ("source_unavailable", "reference", "status", "source_unavailable"),
            ("binding_mismatch", "runtime_binding", "bound_access_scope", "restricted"),
            ("unsupported_request", "runtime_binding", "allowed_operations", ["get_reference"]),
        )
        for code, name, field, value in cases:
            with self.subTest(code=code):
                sample = authority_error_sample(code)
                sample["resolution_context"][name][field] = value
                bind_authority_objects(sample["resolution_context"])
                before = copy.deepcopy(sample)
                self.assert_positive(self.check(sample), "resolve_context_error", "resolve_error_valid")
                self.assertEqual(before, sample)
        sample = authority_error_sample("stale_reference")
        context = sample["resolution_context"]
        context["runtime_binding"]["reference_fingerprint"] = fixtures.fingerprint(b"Synthetic older reference")
        blob = fixtures.encode_test_object(context["runtime_binding"])
        context["authority_context"]["object_bytes"]["runtime_binding"] = blob
        context["authority_context"]["control_plane_selection"]["binding_fingerprint"] = fixtures.fingerprint(blob)
        self.assert_positive(self.check(sample), "resolve_context_error", "resolve_error_valid")

    def test_contradicted_and_unresolved_authority_errors(self):
        for code in ("client_not_allowed", "reference_not_active", "stale_locator", "stale_reference", "binding_mismatch", "unsupported_request"):
            with self.subTest(code=code):
                self.assert_failure(self.check(authority_error_sample(code)), "resolve_error_evidence_mismatch", "$/response/error_code")
        sample = authority_error_sample("client_not_allowed")
        del sample["resolution_context"]["client_profile"]
        self.assert_failure(self.check(sample), "resolve_context_missing", decision=Decision.NEEDS_REVIEW, status="incomplete_resolution_context")
        # 完整 eligible Authority 仍不证明 freshness 错误的客观正向原因。
        self.assert_failure(self.check(authority_error_sample("freshness_verification_required")), "resolve_context_missing", decision=Decision.NEEDS_REVIEW, status="incomplete_resolution_context")

    def test_supported_source_errors_require_corresponding_exchange(self):
        for code in ("source_unavailable", "limit_exceeded"):
            with self.subTest(code=code):
                sample = source_error_sample(code)
                before = copy.deepcopy(sample)
                self.assert_positive(self.check(sample), "resolve_context_error", "resolve_error_valid")
                self.assertEqual(before, sample)
                del sample["resolution_context"]["source_exchanges"]
                self.assert_failure(self.check(sample), "resolve_context_missing", decision=Decision.NEEDS_REVIEW, status="incomplete_resolution_context")

    def test_source_error_code_retryable_and_time_must_match(self):
        for field, value in (("error_code", "not_found"), ("retryable", False), ("observed_at", fixtures.utc_timestamp(6))):
            with self.subTest(field=field):
                sample = source_error_sample("source_unavailable")
                sample["resolution_context"]["source_exchanges"][0]["response"][field] = value
                self.assert_failure(self.check(sample), "resolve_error_evidence_mismatch")

    def test_provenance_error_requires_specific_p2c_findings(self):
        for field in ("source_id", "scope_id", "adapter_id", "operation", "content_fingerprint"):
            with self.subTest(field=field):
                sample = copy.deepcopy(self.sample)
                sample["response"] = fixtures.build_resolve_context_error(sample["request"])
                sample["response"].update(error_code="provenance_mismatch", observed_at=fixtures.utc_timestamp(7))
                del sample["resolution_context"]["resolution_event"]
                exchange = sample["resolution_context"]["source_exchanges"][0]
                value = "stat" if field == "operation" else fixtures.fingerprint(b"Synthetic wrong body") if field == "content_fingerprint" else SENTINELS[2]
                exchange["response"]["provenance"][field] = value
                p2c = source.validate_source_adapter_exchange(exchange["manifest"], exchange["request"], exchange["response"], exact_content_bytes=exchange["exact_content_bytes"], registry=self.registry)
                self.assertEqual(Decision.REJECT, p2c.decision)
                code = "source_adapter_fingerprint_mismatch" if field == "content_fingerprint" else "source_adapter_provenance_mismatch"
                self.assertEqual({(code, "$/response/provenance/" + field)}, {(i.code, i.path) for i in p2c.errors})
                self.assert_positive(self.check(sample), "resolve_context_error", "resolve_error_valid")
        # 任意 P2C 拒绝不能冒充 provenance 错误证据。
        sample = copy.deepcopy(self.sample)
        sample["response"] = fixtures.build_resolve_context_error(sample["request"])
        sample["response"].update(error_code="provenance_mismatch", observed_at=fixtures.utc_timestamp(7))
        del sample["resolution_context"]["resolution_event"]
        sample["resolution_context"]["source_exchanges"][0]["response"]["request_id"] = SENTINELS[2]
        self.assert_failure(self.check(sample), "resolve_error_evidence_mismatch")

    def test_error_mode_forbids_positive_or_unrelated_source_evidence(self):
        sample = authority_error_sample("reference_not_active")
        sample["resolution_context"]["reference"]["status"] = "paused"
        bind_authority_objects(sample["resolution_context"])
        sample["resolution_context"]["source_exchanges"] = self.sample["resolution_context"]["source_exchanges"]
        with patch.object(resolve, "validate_source_adapter_exchange", wraps=source.validate_source_adapter_exchange) as delegate:
            self.assert_failure(self.check(sample), "resolve_invalid_object", "$/resolution_context/source_exchanges")
        delegate.assert_not_called()
        for sample in (authority_error_sample("reference_not_active"), source_error_sample("source_unavailable")):
            with self.subTest(code=sample["response"]["error_code"]):
                sample["resolution_context"]["resolution_event"] = self.sample["resolution_context"]["resolution_event"]
                self.assert_failure(self.check(sample), "resolve_invalid_object", "$/resolution_context/resolution_event")

    def test_priority_reject_over_missing_resolution_evidence(self):
        self.sample["response"]["request_id"] = SENTINELS[2]
        del self.sample["resolution_context"]["source_exchanges"]
        result = self.check()
        self.assert_failure(result, "resolve_request_linkage_mismatch")
        self.assertIn("resolve_context_missing", {issue.code for issue in result.errors})

    def test_priority_reject_over_delegated_error_and_error_over_missing(self):
        for contradiction in (True, False):
            with self.subTest(contradiction=contradiction):
                sample = copy.deepcopy(self.sample)
                if contradiction:
                    sample["response"]["request_id"] = SENTINELS[2]
                del sample["resolution_context"]["resolution_event"]
                observed = []
                def delegated(*args, **kwargs):
                    with patch.object(self.registry, "validator_for", side_effect=RuntimeError(SENTINELS[0])):
                        result = source.validate_source_adapter_exchange(*args, **kwargs)
                    observed.append(result)
                    return result
                with patch.object(resolve, "validate_source_adapter_exchange", side_effect=delegated):
                    result = self.check(sample)
                self.assertEqual([Decision.ERROR], [item.decision for item in observed])
                if contradiction:
                    self.assert_failure(result, "resolve_request_linkage_mismatch")
                else:
                    self.assert_failure(result, "resolve_validation_unavailable", decision=Decision.ERROR, status="validation_unavailable")
                self.assertTrue({"resolve_context_missing", "resolve_validation_unavailable"} <= {issue.code for issue in result.errors})

    def test_same_registry_reaches_both_delegates_without_new_instances(self):
        with patch.object(resolve, "SchemaRegistry", side_effect=AssertionError("unexpected registry")) as resolve_factory, patch.object(authority, "SchemaRegistry", side_effect=AssertionError("unexpected registry")) as authority_factory, patch.object(source, "SchemaRegistry", side_effect=AssertionError("unexpected registry")) as source_factory, patch.object(resolve, "validate_reference_authority", wraps=authority.validate_reference_authority) as p2d, patch.object(resolve, "validate_source_adapter_exchange", wraps=source.validate_source_adapter_exchange) as p2c, patch.object(self.registry, "validator_for", wraps=self.registry.validator_for) as strict:
            self.assert_positive(self.check(two_entry_sample()))
            self.assert_positive(resolve.validate_resolve_context_object(self.sample["request"], "resolve_context_request", self.registry), "resolve_context_request", "object_valid")
        for factory in (resolve_factory, authority_factory, source_factory):
            factory.assert_not_called()
        for delegate in (p2d, p2c):
            self.assertTrue(delegate.called)
            self.assertTrue(all(item.kwargs["registry"] is self.registry for item in delegate.call_args_list))
        self.assertTrue({"resolve_context_request", "resolve_context_result", "trusted_client_profile", "registered_context_reference", "runtime_binding", "source_adapter_manifest", "source_adapter_request", "source_adapter_result"} <= {item.args[0] for item in strict.call_args_list})

    def test_diagnostics_do_not_echo_private_values_or_exception_text(self):
        for field, value, code in (("text", SENTINELS[0], "resolve_payload_mismatch"), ("entry_point", SENTINELS[1], "resolve_entry_selection_mismatch")):
            with self.subTest(field=field):
                sample = copy.deepcopy(self.sample)
                sample["response"]["payload"][0][field] = value
                self.assert_failure(self.check(sample), code)
        self.sample["response"]["request_id"] = SENTINELS[2]
        self.assert_failure(self.check(), "resolve_request_linkage_mismatch")
        sample = resolve_sample()
        exchange = sample["resolution_context"]["source_exchanges"][0]
        exchange["response"] = fixtures.build_source_adapter_result(exchange["request"], text=SENTINELS[0])
        exchange["response"]["provenance"]["observed_at"] = fixtures.utc_timestamp(7)
        exchange["exact_content_bytes"] = SENTINELS[0].encode("utf-8")
        self.assert_failure(self.check(sample), "resolve_payload_mismatch")
        for delegate in ("validate_reference_authority", "validate_source_adapter_exchange"):
            with self.subTest(delegate=delegate), patch.object(resolve, delegate, side_effect=RuntimeError(" ".join(SENTINELS))):
                self.assert_failure(self.check(resolve_sample()), "resolve_validation_unavailable", decision=Decision.ERROR, status="validation_unavailable")

    def test_safe_timestamp_and_exchange_array_resource_ceilings(self):
        self.sample["resolution_context"]["resolved_at"] = "2" * 257
        self.assert_failure(self.check(), "resolve_resource_limit_exceeded", decision=Decision.ERROR, status="validation_unavailable")
        sample = resolve_sample()
        # 129 个空字典足够触发 128 条私有上限，不分配正文或大块 bytes。
        sample["resolution_context"]["source_exchanges"] = [{} for _ in range(129)]
        self.assert_failure(self.check(sample), "resolve_resource_limit_exceeded", decision=Decision.ERROR, status="validation_unavailable")


if __name__ == "__main__":
    unittest.main()
