"""Context Bridge（上下文桥）显式验证路由对旧合同的非干扰证据。

只读取静态 Manifest（清单）与仓库内合成样本；不调用真实来源、传输或激活操作。
object_valid 仅表示对象有效，不产生治理效力、自动采用或运行时启用。
"""

import copy
import io
import json
import unittest
from contextlib import ExitStack, redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

import xingshu_core
import yaml
from xingshu_core import cli, validator as generic
from xingshu_core import authority_validation as authority
from xingshu_core import context_bridge_validation as bridge
from xingshu_core import resolve_context_validation as resolve
from xingshu_core import source_adapter_validation as source
from xingshu_core.decisions import Decision
from xingshu_core.schema_registry import CONTEXT_BRIDGE_SCHEMA_REFS, SCHEMA_REFS, SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
LEGACY_REFS = {
    "memory_entry": "schemas/v0.3/memory-entry.schema.json",
    "knowledge_object": "schemas/v0.3/knowledge-object.schema.json",
    "migration_provenance": "schemas/v0.3/migration-provenance.schema.json",
}
LEGACY_VALID = (
    ("memory_entry", "examples/v0.4/memory-valid.json", "current_valid"),
    ("knowledge_object", "tests/fixtures/v0.3/knowledge-object/main-valid.json", "accepted"),
    ("migration_provenance", "examples/v0.4/migration-valid.json", "accepted"),
)
SENTINELS = (
    "SYNTHETIC_P3_PRIVATE_TEXT_SENTINEL",
    "SYNTHETIC_P3_PRIVATE_LOCATOR_SENTINEL",
    "SYNTHETIC_P3_PRIVATE_ID_SENTINEL",
)


def load_fixture(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class ContextBridgeNonInterferenceTests(unittest.TestCase):
    def setUp(self):
        self.registry = SchemaRegistry()

    def test_internal_discovery_leaves_legacy_registry_identity_unchanged(self):
        legacy_before = copy.deepcopy(SCHEMA_REFS)
        candidate_before = copy.deepcopy(CONTEXT_BRIDGE_SCHEMA_REFS)
        self.assertEqual(LEGACY_REFS, self.registry.discover())
        self.assertEqual(16, len(self.registry.discover_context_bridge()))
        self.assertEqual(11, len(set(CONTEXT_BRIDGE_SCHEMA_REFS.values())))
        self.assertEqual(LEGACY_REFS, self.registry.discover())
        for route, ref in LEGACY_REFS.items():
            with self.subTest(route=route):
                self.assertEqual(ref, self.registry.schema_ref_for(route))
                self.assertEqual(self.registry.load_schema(route), self.registry.validator_for(route).schema)
        self.assertEqual(legacy_before, SCHEMA_REFS)
        self.assertEqual(candidate_before, CONTEXT_BRIDGE_SCHEMA_REFS)

    def test_three_legacy_valid_objects_keep_results_and_inputs(self):
        for route, path, status in LEGACY_VALID:
            with self.subTest(route=route):
                record = load_fixture(path)
                before = copy.deepcopy(record)
                first = generic.validate_record(record, registry=self.registry)
                self.registry.discover_context_bridge()
                second = generic.validate_record(record, registry=self.registry)
                self.assertEqual(first, second)
                self.assertEqual((Decision.PASS, status, route, LEGACY_REFS[route], ()), (second.decision, second.status, second.record_type, second.schema_ref, second.errors))
                self.assertEqual(before, record)

    def test_three_legacy_invalid_fixtures_keep_diagnostic_family(self):
        self.registry.discover_context_bridge()
        cases = (
            ("memory_entry", "tests/fixtures/v0.3/memory-entry/memory-candidate-without-source-invalid.json", "schema_minItems"),
            ("knowledge_object", "tests/fixtures/v0.3/knowledge-object/cross-platform-path-reuse-invalid.json", "cross_platform_path_reuse"),
            ("migration_provenance", "tests/fixtures/v0.3/migration-provenance/migration-drops-source-without-provenance-invalid.json", "source_without_mapping_or_omission"),
        )
        for route, path, code in cases:
            with self.subTest(route=route):
                record = load_fixture(path)
                before = copy.deepcopy(record)
                result = generic.validate_record(record, registry=self.registry)
                self.assertEqual((Decision.REJECT, "rejected", route, 3), (result.decision, result.status, result.record_type, result.exit_code))
                self.assertIn(code, {issue.code for issue in result.errors})
                self.assertEqual(before, record)

    def test_legacy_privacy_scan_is_preserved_for_all_three_routes(self):
        for route, path, _ in LEGACY_VALID:
            for sentinel in SENTINELS:
                with self.subTest(route=route, sentinel=sentinel):
                    record = load_fixture(path)
                    record["payload"] = sentinel
                    before = copy.deepcopy(record)
                    result = generic.validate_record(record, registry=self.registry)
                    self.assertEqual(Decision.REJECT, result.decision)
                    self.assertEqual(["privacy_boundary_violation"], [issue.code for issue in result.errors])
                    self.assertNotIn(sentinel, str(result) + json.dumps(result.to_dict()))
                    self.assertEqual(before, record)

    def test_legacy_cli_exit_and_diagnostics_remain_unchanged(self):
        self.registry.discover_context_bridge()
        cases = tuple((path, 0, "pass", status, None) for _, path, status in LEGACY_VALID) + (
            ("examples/v0.4/memory-needs-review.json", 2, "needs_review", "needs_review", "evidence_not_current"),
            ("tests/fixtures/v0.3/knowledge-object/cross-platform-path-reuse-invalid.json", 3, "reject", "rejected", "cross_platform_path_reuse"),
        )
        for path, exit_code, decision, status, code in cases:
            with self.subTest(path=path):
                input_path = ROOT / path
                before = input_path.read_bytes()
                stdout, stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    actual_exit = cli.main(["validate", str(input_path), "--json"])
                report = json.loads(stdout.getvalue())
                self.assertEqual(exit_code, actual_exit)
                self.assertEqual((decision, status), (report["decision"], report["status"]))
                self.assertEqual("", stderr.getvalue())
                if code is not None:
                    self.assertIn(code, {issue["code"] for issue in report["errors"]})
                self.assertEqual(before, input_path.read_bytes())

    def test_explicit_candidate_routing_does_not_execute_cross_evidence_actions(self):
        candidate = load_fixture("tests/fixtures/context-bridge/context-candidate-valid.json")
        derived = load_fixture("tests/fixtures/context-bridge/derived-provider-metadata-valid.json")
        before = copy.deepcopy((candidate, derived))
        cross = (
            (bridge, "validate_registration_validation"), (bridge, "validate_registration_chain"),
            (bridge, "validate_reference_transition"), (authority, "validate_reference_authority"),
            (source, "validate_source_adapter_exchange"), (resolve, "validate_resolve_context_exchange"),
        )
        with ExitStack() as stack:
            spies = [stack.enter_context(patch.object(module, name, side_effect=AssertionError("cross evidence invoked"))) for module, name in cross]
            for record in (candidate, derived):
                result = generic.validate_record(record, record["object_kind"], self.registry)
                self.assertEqual((Decision.PASS, "object_valid", ()), (result.decision, result.status, result.errors))
            for spy in spies:
                spy.assert_not_called()
        self.assertEqual(before, (candidate, derived))
        self.assertEqual(("derived", True, "lookup_hint_only", False), (derived["authority_class"], derived["rebuildable"], derived["usage_class"], derived["final_authority"]))
        self.assertFalse(any(name.startswith("validate_derived") for name in xingshu_core.__all__))
        self.assertEqual(LEGACY_REFS, self.registry.discover())

    def test_internal_registry_awareness_never_exposes_error_route(self):
        self.registry.validator_for("resolve_context_error")
        record = {
            "schema_version": "context-bridge-candidate", "object_kind": "resolve_context_error",
            "request_id": "synthetic:p3:request:01", "reference_id": "synthetic:p3:reference:01",
            "error_code": "source_unavailable", "retryable": True, "observed_at": "2026-01-01T00:00:07Z",
        }
        self.assertEqual([], list(self.registry.validator_for("resolve_context_error").iter_errors(record)))
        before = copy.deepcopy(record)
        result = generic.validate_record(record, registry=self.registry)
        self.assertEqual((Decision.REJECT, "rejected"), (result.decision, result.status))
        self.assertEqual(["candidate_unsupported_route"], [issue.code for issue in result.errors])
        self.assertEqual(before, record)
        self.assertNotIn("resolve_context_error", generic._PUBLIC_ROUTES)
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli.main(["validate", "synthetic-not-read.json", "--type", "resolve_context_error", "--json"])
        self.assertEqual(4, code)
        self.assertEqual("", stdout.getvalue())
        self.assertEqual("ERROR\nstatus: input_error\nmessage: invalid command-line usage\n", stderr.getvalue())

    def test_malformed_candidate_is_not_repaired_or_echoed(self):
        for sentinel in SENTINELS:
            with self.subTest(sentinel=sentinel):
                record = {"object_kind": sentinel, "schema_version": "context-bridge-candidate"}
                before = copy.deepcopy(record)
                result = generic.validate_record(record, registry=self.registry)
                self.assertEqual(Decision.REJECT, result.decision)
                self.assertEqual(["candidate_unsupported_route"], [issue.code for issue in result.errors])
                self.assertNotIn(sentinel, str(result) + json.dumps(result.to_dict()))
                self.assertEqual(before, record)


class ContextBridgeManifestIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.manifest = yaml.safe_load((ROOT / "CORE_MANIFEST.yaml").read_text())

    def test_registered_capability_is_optional_and_has_no_activation_effect(self):
        item = self.manifest["capabilities"]["context_bridge_validation"]
        self.assertEqual("0.1", item["version"])
        self.assertEqual("candidate", item["status"])
        self.assertIs(False, item["enabled_by_default"])
        self.assertEqual("additive_optional", item["backward_compatibility"])
        self.assertEqual({"runnable_validation_cli": ">=0.4"}, item["dependencies"])
        for field in ("governance_effect", "authorization_effect", "activation_effect"):
            with self.subTest(field=field):
                self.assertEqual("none", item[field])
        self.assertEqual("none", self.manifest["governance_effect"])
        self.assertEqual("not_active", self.manifest["activation_state"])

    def test_disabled_capability_still_allows_explicit_object_cli_validation(self):
        # 默认禁用约束自动采用，不隐藏已经公开的显式单对象验证入口。
        before = copy.deepcopy(self.manifest)
        self.assertIs(False, self.manifest["capabilities"]["context_bridge_validation"]["enabled_by_default"])
        path = ROOT / "tests/fixtures/context-bridge/context-candidate-valid.json"
        input_bytes = path.read_bytes()
        manifest_bytes = (ROOT / "CORE_MANIFEST.yaml").read_bytes()
        cross = (
            (bridge, "validate_registration_validation"), (bridge, "validate_registration_chain"),
            (bridge, "validate_reference_transition"), (authority, "validate_reference_authority"),
            (source, "validate_source_adapter_exchange"), (resolve, "validate_resolve_context_exchange"),
        )
        stdout, stderr = io.StringIO(), io.StringIO()
        with ExitStack() as stack:
            spies = []
            for module, name in cross:
                spies.append(stack.enter_context(patch.object(module, name, side_effect=AssertionError("cross evidence invoked"))))
                spies.append(stack.enter_context(patch.object(generic, name, create=True, side_effect=AssertionError("cross evidence invoked"))))
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = cli.main(["validate", str(path), "--type", "context_candidate", "--json"])
            for spy in spies:
                spy.assert_not_called()
        report = json.loads(stdout.getvalue())
        self.assertEqual(0, code)
        self.assertEqual("", stderr.getvalue())
        self.assertEqual(("pass", "object_valid", "context_candidate", []),
                         (report["decision"], report["status"], report["record_type"], report["errors"]))
        self.assertEqual(input_bytes, path.read_bytes())
        self.assertEqual(manifest_bytes, (ROOT / "CORE_MANIFEST.yaml").read_bytes())
        self.assertEqual(before, self.manifest)
        self.assertEqual("not_active", self.manifest["activation_state"])
        # 这里只验证静态清单和单对象合同，不提供来源访问、身份认证或运行时就绪证明。

    def test_manifest_schema_files_do_not_expand_public_routes(self):
        registry = SchemaRegistry()
        internal = registry.discover_context_bridge()
        expected_public = (
            "context_candidate", "context_registration_proposal", "context_validation_artifact",
            "human_authorization_evidence", "registered_context_reference", "context_reference_transition",
            "source_adapter_manifest", "source_adapter_request", "source_adapter_result", "source_adapter_error",
            "trusted_client_profile", "runtime_binding", "resolve_context_request", "resolve_context_result",
            "derived_provider_metadata",
        )
        self.assertEqual(16, len(internal))
        self.assertIn("resolve_context_error", internal)
        self.assertEqual(11, len(set(internal.values())))
        refs = self.manifest["capabilities"]["context_bridge_validation"]["schema_refs"]
        self.assertEqual(11, len(refs))
        self.assertEqual(set(internal.values()), set(refs))
        self.assertEqual(15, len(expected_public))
        self.assertEqual(tuple(LEGACY_REFS) + expected_public, generic._PUBLIC_ROUTES)
        self.assertNotIn("resolve_context_error", generic._PUBLIC_ROUTES)
        self.assertEqual(LEGACY_REFS, registry.discover())


if __name__ == "__main__":
    unittest.main()
