import copy
import json
import runpy
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

from xingshu_core import Decision, validate_record
from xingshu_core import authority_validation as authority
from xingshu_core import context_bridge_validation as bridge
from xingshu_core import resolve_context_validation as resolve
from xingshu_core import source_adapter_validation as source
from xingshu_core import validator as generic
from xingshu_core.schema_registry import SchemaRegistry


ROOT = Path(__file__).resolve().parents[2]


def load(path):
    return json.loads((ROOT / path).read_text())


class ValidatorRuntimeTests(unittest.TestCase):
    def test_valid_memory_passes(self):
        result = validate_record(load("examples/v0.4/memory-valid.json"))
        self.assertEqual(Decision.PASS, result.decision)
        self.assertEqual("current_valid", result.status)
        self.assertEqual(0, result.exit_code)

    def test_stale_memory_needs_review(self):
        result = validate_record(load("examples/v0.4/memory-needs-review.json"))
        self.assertEqual(Decision.NEEDS_REVIEW, result.decision)
        self.assertEqual("needs_review", result.status)
        self.assertEqual(2, result.exit_code)

    def test_schema_invalid_memory_is_rejected(self):
        result = validate_record(
            load("tests/fixtures/v0.3/memory-entry/memory-candidate-without-source-invalid.json")
        )
        self.assertEqual(Decision.REJECT, result.decision)
        self.assertEqual(3, result.exit_code)
        self.assertTrue(result.errors)

    def test_valid_migration_passes_without_claiming_runtime_verified(self):
        record = load("examples/v0.4/migration-valid.json")
        result = validate_record(record)
        self.assertEqual(Decision.PASS, result.decision)
        self.assertEqual("accepted", result.status)
        self.assertEqual("pending_verification", record["runtime_validation_state"])

    def test_knowledge_object_semantic_violation_is_rejected(self):
        record = load("tests/fixtures/v0.3/knowledge-object/cross-platform-path-reuse-invalid.json")
        result = validate_record(record)
        self.assertEqual(Decision.REJECT, result.decision)
        self.assertIn("cross_platform_path_reuse", {issue.code for issue in result.errors})

    def test_migration_semantic_violation_is_rejected(self):
        record = load(
            "tests/fixtures/v0.3/migration-provenance/migration-drops-source-without-provenance-invalid.json"
        )
        result = validate_record(record)
        self.assertEqual(Decision.REJECT, result.decision)
        self.assertIn(
            "source_without_mapping_or_omission",
            {issue.code for issue in result.errors},
        )

    def test_unknown_record_type_fails_closed(self):
        result = validate_record({"schema_version": "0.3", "record_type": "unknown_object"})
        self.assertEqual(Decision.REJECT, result.decision)
        self.assertEqual("unknown_record_type", result.errors[0].code)

    def test_validation_does_not_modify_record(self):
        record = load("examples/v0.4/memory-valid.json")
        before = copy.deepcopy(record)
        validate_record(record)
        self.assertEqual(before, record)

    def test_error_output_does_not_echo_private_value(self):
        record = load("examples/v0.4/memory-valid.json")
        record["secret"] = "PRIVATE_VALUE_SENTINEL"
        result = validate_record(record)
        rendered = json.dumps(result.to_dict())
        self.assertEqual(Decision.REJECT, result.decision)
        self.assertEqual("privacy_boundary_violation", result.errors[0].code)
        self.assertNotIn("PRIVATE_VALUE_SENTINEL", rendered)

    def test_timezone_naive_record_is_rejected(self):
        record = load("examples/v0.4/memory-valid.json")
        record["created_at"] = "2026-01-01T00:00:00"
        result = validate_record(record)
        self.assertEqual(Decision.REJECT, result.decision)
        self.assertIn("schema_format", {issue.code for issue in result.errors})


PUBLIC_CANDIDATE_FAMILIES = (
    (bridge.validate_context_bridge_object, "context_bridge_schema_invalid", "context_bridge_validation_unavailable", (
        "context_candidate", "context_registration_proposal", "context_validation_artifact",
        "human_authorization_evidence", "registered_context_reference", "context_reference_transition",
    )),
    (source.validate_source_adapter_object, "source_adapter_schema_invalid", "source_adapter_validation_unavailable", (
        "source_adapter_manifest", "source_adapter_request", "source_adapter_result", "source_adapter_error",
    )),
    (authority.validate_authority_object, "authority_schema_invalid", "authority_validation_unavailable", (
        "trusted_client_profile", "runtime_binding",
    )),
    (resolve.validate_resolve_context_object, "resolve_schema_invalid", "resolve_validation_unavailable", (
        "resolve_context_request", "resolve_context_result",
    )),
)
SENTINELS = (
    "SYNTHETIC_P3_PRIVATE_TEXT_SENTINEL",
    "SYNTHETIC_P3_PRIVATE_LOCATOR_SENTINEL",
    "SYNTHETIC_P3_PRIVATE_ID_SENTINEL",
)


class CandidateValidatorIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = SchemaRegistry()
        # 仅复用已冻结 P3A 的样本组装函数，不执行其测试或复制验证算法。
        cls.objects = runpy.run_path(str(ROOT / "tests/conformance/context-bridge/test_contract_schemas.py"))["positive_objects"]()

    def assert_failure(self, result, code, decision=Decision.REJECT, status="rejected"):
        self.assertEqual(decision, result.decision)
        self.assertEqual(status, result.status)
        self.assertEqual([code], [issue.code for issue in result.errors])
        rendered = str(result) + json.dumps(result.to_dict(), ensure_ascii=False)
        for sentinel in SENTINELS:
            self.assertNotIn(sentinel, rendered)

    def raw_result(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic-record.json"
            path.write_text(text, encoding="utf-8")
            before = path.read_bytes()
            result = generic.validate_file(path, registry=self.registry)
            self.assertEqual(before, path.read_bytes())
            return result

    def test_public_inventory_is_eighteen_with_fifteen_candidates(self):
        expected = tuple(route for _, _, _, routes in PUBLIC_CANDIDATE_FAMILIES for route in routes) + ("derived_provider_metadata",)
        self.assertEqual(15, len(expected))
        self.assertEqual(expected, tuple(generic._CANDIDATE_VALIDATORS))
        self.assertEqual(("memory_entry", "knowledge_object", "migration_provenance") + expected, generic._PUBLIC_ROUTES)
        self.assertEqual(18, len(generic._PUBLIC_ROUTES))
        self.assertNotIn("resolve_context_error", generic._PUBLIC_ROUTES)
        self.assertEqual(["derived_provider_metadata"], [route for route, function in generic._CANDIDATE_VALIDATORS.items() if function is None])
        for function, _, _, routes in PUBLIC_CANDIDATE_FAMILIES:
            for route in routes:
                with self.subTest(route=route):
                    self.assertIs(function, generic._CANDIDATE_VALIDATORS[route])

    def test_each_specialized_route_calls_one_family_and_preserves_result_identity(self):
        for function, _, _, routes in PUBLIC_CANDIDATE_FAMILIES:
            for route in routes:
                with self.subTest(route=route):
                    record = copy.deepcopy(self.objects[route])
                    before, returned = copy.deepcopy(record), []
                    def delegate(*args, **kwargs):
                        result = function(*args, **kwargs)
                        returned.append(result)
                        return result
                    selected = Mock(side_effect=delegate)
                    others = {name: Mock(side_effect=AssertionError("unexpected alternate route")) for name in generic._CANDIDATE_VALIDATORS if name != route}
                    with patch.dict(generic._CANDIDATE_VALIDATORS, {**others, route: selected}), patch.object(generic, "_forbidden_key_issues", side_effect=AssertionError("legacy scan on candidate")), patch.object(generic, "_schema_issues", side_effect=AssertionError("legacy schema pass on candidate")), patch.object(generic, "SchemaRegistry", side_effect=AssertionError("extra registry")) as factory:
                        result = generic.validate_record(record, route, self.registry)
                    selected.assert_called_once_with(record, route, registry=self.registry)
                    factory.assert_not_called()
                    for alternate in others.values():
                        alternate.assert_not_called()
                    self.assertIs(returned[0], result)
                    self.assertEqual((Decision.PASS, route, "context-bridge-candidate", ()), (result.decision, result.record_type, result.schema_version, result.errors))
                    self.assertEqual("error_envelope_valid" if route == "source_adapter_error" else "object_valid", result.status)
                    self.assertEqual(before, record)

    def test_schema_invalid_keeps_each_family_code_and_input_unchanged(self):
        for _, code, _, routes in PUBLIC_CANDIDATE_FAMILIES:
            for route in routes:
                with self.subTest(route=route):
                    record = copy.deepcopy(self.objects[route])
                    record["synthetic_extra"] = SENTINELS[0]
                    before = copy.deepcopy(record)
                    self.assert_failure(generic.validate_record(record, registry=self.registry), code)
                    self.assertEqual(before, record)

    def test_specialized_unavailability_is_not_normalized(self):
        for _, _, code, routes in PUBLIC_CANDIDATE_FAMILIES:
            for route in routes:
                with self.subTest(route=route), patch.object(self.registry, "validator_for", side_effect=RuntimeError(SENTINELS[0])):
                    result = generic.validate_record(self.objects[route], registry=self.registry)
                self.assert_failure(result, code, Decision.ERROR, "validation_unavailable")

    def test_specialized_resource_findings_are_not_normalized(self):
        with patch.object(self.registry, "validator_for", side_effect=MemoryError(SENTINELS[0])):
            result = generic.validate_record(self.objects["context_candidate"], registry=self.registry)
        self.assert_failure(result, "context_bridge_resource_limit_exceeded", Decision.ERROR, "validation_unavailable")
        for route, section, field, code in (
            ("trusted_client_profile", None, "created_at", "authority_resource_limit_exceeded"),
            ("resolve_context_result", "freshness", "verified_at", "resolve_resource_limit_exceeded"),
        ):
            with self.subTest(route=route):
                record = copy.deepcopy(self.objects[route])
                (record if section is None else record[section])[field] = "2" * 257
                self.assert_failure(generic.validate_record(record, registry=self.registry), code, Decision.ERROR, "validation_unavailable")

    def test_derived_branch_is_schema_only_with_its_own_generic_diagnostic(self):
        record = copy.deepcopy(self.objects["derived_provider_metadata"])
        before = copy.deepcopy(record)
        alternatives = {route: Mock(side_effect=AssertionError("family called for derived")) for route in generic._CANDIDATE_VALIDATORS if route != "derived_provider_metadata"}
        with patch.dict(generic._CANDIDATE_VALIDATORS, alternatives), patch.object(self.registry, "validator_for", wraps=self.registry.validator_for) as strict:
            result = generic.validate_record(record, registry=self.registry)
        strict.assert_called_once_with("derived_provider_metadata")
        for alternate in alternatives.values():
            alternate.assert_not_called()
        self.assertEqual((Decision.PASS, "object_valid", "derived_provider_metadata", "context-bridge-candidate", "schemas/candidate/context-bridge/derived-provider-metadata.schema.json", ()), (result.decision, result.status, result.record_type, result.schema_version, result.schema_ref, result.errors))
        self.assertEqual(before, record)
        record["final_authority"] = True
        self.assert_failure(generic.validate_record(record, registry=self.registry), "candidate_schema_invalid")

    def test_generic_integration_exceptions_keep_generic_codes(self):
        for failure, code in (
            (RuntimeError(SENTINELS[0]), "candidate_validation_unavailable"),
            (MemoryError(SENTINELS[0]), "validation_resource_limit_exceeded"),
            (RecursionError(SENTINELS[0]), "validation_resource_limit_exceeded"),
        ):
            with self.subTest(failure=type(failure).__name__):
                # 通用层创建 Registry 时失败，尚未进入任何专用验证器。
                with patch.object(generic, "SchemaRegistry", side_effect=failure):
                    self.assert_failure(generic.validate_record(self.objects["context_candidate"]), code, Decision.ERROR, "validation_unavailable")
                # Derived 分支不经过专用函数，严格验证异常由通用层处理。
                with patch.object(self.registry, "validator_for", side_effect=failure):
                    self.assert_failure(generic.validate_record(self.objects["derived_provider_metadata"], registry=self.registry), code, Decision.ERROR, "validation_unavailable")

    def test_internal_resolve_error_never_becomes_generic_public(self):
        self.assertIsNotNone(self.registry.validator_for("resolve_context_error"))
        record = self.objects["resolve_context_error"]
        for override in (None, "resolve_context_error"):
            with self.subTest(override=override):
                self.assert_failure(generic.validate_record(record, override, self.registry), "candidate_unsupported_route")
        self.assert_failure(self.raw_result(json.dumps(record)), "candidate_unsupported_route")

    def test_candidate_root_duplicates_use_raw_file_boundary(self):
        raw = json.dumps(self.objects["context_candidate"])
        cases = (
            '{"object_kind":"context_candidate",' + raw[1:],
            '{"object_kind":"synthetic_unsupported",' + raw[1:],
            '{"record_type":"memory_entry",' + raw[1:],
            '{"record_type":"memory_entry","record_type":"knowledge_object",' + raw[1:],
        )
        for text in cases:
            with self.subTest(prefix=text[:65]):
                self.assert_failure(self.raw_result(text), "candidate_discriminator_conflict")
        # 已解析 Mapping 没有重复键历史；不能据此宣称可恢复 raw duplicates。
        self.assertEqual(Decision.PASS, generic.validate_record(json.loads(cases[0]), registry=self.registry).decision)

    def test_parsed_mixed_discriminators_and_route_mismatch_never_repair_input(self):
        cases = (
            ({**self.objects["context_candidate"], "record_type": "memory_entry"}, None, "candidate_discriminator_conflict"),
            (copy.deepcopy(self.objects["context_candidate"]), "trusted_client_profile", "candidate_route_mismatch"),
            ({"schema_version": "context-bridge-candidate"}, "context_candidate", "candidate_route_mismatch"),
            ({"object_kind": SENTINELS[2]}, None, "candidate_unsupported_route"),
        )
        for record, override, code in cases:
            with self.subTest(code=code):
                before = copy.deepcopy(record)
                self.assert_failure(generic.validate_record(record, override, self.registry), code)
                self.assertEqual(before, record)

    def test_legacy_duplicate_record_type_retains_last_value(self):
        for route, path, status in (
            ("memory_entry", "examples/v0.4/memory-valid.json", "current_valid"),
            ("knowledge_object", "tests/fixtures/v0.3/knowledge-object/main-valid.json", "accepted"),
            ("migration_provenance", "examples/v0.4/migration-valid.json", "accepted"),
        ):
            with self.subTest(route=route):
                raw = json.dumps(load(path))
                result = self.raw_result('{"record_type":"synthetic_unsupported",' + raw[1:])
                self.assertEqual((Decision.PASS, status, route), (result.decision, result.status, result.record_type))
                self.assert_failure(self.raw_result(raw[:-1] + ',"record_type":"synthetic_unsupported"}'), "unknown_record_type")

    def test_candidate_payload_is_not_subject_to_legacy_forbidden_key_scan(self):
        for route in ("source_adapter_result", "resolve_context_result"):
            with self.subTest(route=route):
                self.assertIn("payload", self.objects[route])
                self.assertEqual(Decision.PASS, generic.validate_record(self.objects[route], registry=self.registry).decision)
        record = load("examples/v0.4/memory-valid.json")
        record["payload"] = SENTINELS[0]
        self.assert_failure(generic.validate_record(record, registry=self.registry), "privacy_boundary_violation")

    def test_registered_reference_is_only_a_p2b_object_contract(self):
        record = copy.deepcopy(self.objects["registered_context_reference"])
        record.update(status="paused", allowed_clients=[])
        before = copy.deepcopy(record)
        result = generic.validate_record(record, registry=self.registry)
        self.assertEqual((Decision.PASS, "object_valid", "registered_context_reference", ()), (result.decision, result.status, result.record_type, result.errors))
        self.assertEqual(before, record)
        # 无跨证据上下文且 deny-all 仍可单对象有效；不能推导登记链或准入通过。

    def test_generic_object_validation_never_calls_cross_evidence_apis(self):
        cross = (
            (bridge, "validate_registration_validation"), (bridge, "validate_registration_chain"),
            (bridge, "validate_reference_transition"), (authority, "validate_reference_authority"),
            (resolve, "validate_resolve_context_exchange"), (source, "validate_source_adapter_exchange"),
        )
        with ExitStack() as stack:
            spies = []
            for module, name in cross:
                spies.append(stack.enter_context(patch.object(module, name, side_effect=AssertionError("cross evidence invoked"))))
                spies.append(stack.enter_context(patch.object(generic, name, create=True, side_effect=AssertionError("cross evidence invoked"))))
            for route in generic._CANDIDATE_VALIDATORS:
                with self.subTest(route=route):
                    self.assertEqual(Decision.PASS, generic.validate_record(self.objects[route], registry=self.registry).decision)
            for spy in spies:
                spy.assert_not_called()

    def test_synthetic_private_values_are_not_echoed(self):
        for sentinel in SENTINELS:
            with self.subTest(sentinel=sentinel):
                record = copy.deepcopy(self.objects["context_candidate"])
                record["synthetic_extra"] = sentinel
                self.assert_failure(generic.validate_record(record, registry=self.registry), "context_bridge_schema_invalid")
                self.assert_failure(generic.validate_record({"object_kind": sentinel}, registry=self.registry), "candidate_unsupported_route")


if __name__ == "__main__":
    unittest.main()
