"""P2D 永久回归：所供上下文自洽不认证真实调用者、会话或控制平面。

PASS 不建立 Source 权限、真实传输、运行时激活或 Resolve 成功。
"""

import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from xingshu_core import authority_validation as authority
from xingshu_core.decisions import Decision
from xingshu_core.schema_registry import SchemaRegistry

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/support"))
import context_bridge_fixtures as fixtures  # noqa: E402

SENTINELS = (
    "SYNTHETIC_P3_PRIVATE_TEXT_SENTINEL",
    "SYNTHETIC_P3_PRIVATE_LOCATOR_SENTINEL",
    "SYNTHETIC_P3_PRIVATE_ID_SENTINEL",
)
REFS = {
    "trusted_client_profile": "schemas/candidate/context-bridge/trusted-client-profile.schema.json",
    "runtime_binding": "schemas/candidate/context-bridge/runtime-binding.schema.json",
    "registered_context_reference": "schemas/candidate/context-bridge/registered-context-reference.schema.json",
}


def authority_sample():
    """明确装配一组静态声明，不计算资格或修复待测反例。"""
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
    profile_bytes = fixtures.encode_test_object(profile)
    reference_bytes = fixtures.encode_test_object(reference)
    binding = fixtures.build_runtime_binding(
        profile, reference, profile_bytes=profile_bytes, reference_bytes=reference_bytes,
    )
    context = {
        "object_bytes": {
            "trusted_client_profile": profile_bytes,
            "registered_context_reference": reference_bytes,
            "runtime_binding": fixtures.encode_test_object(binding),
        },
        "control_plane_selection": {
            "client_id": profile["client_id"],
            "binding_fingerprint": fixtures.fingerprint(fixtures.encode_test_object(binding)),
            "transport_binding_id": binding["transport_binding_id"],
            "transport_class": binding["transport_class"],
        },
        "operation": "resolve_context", "evaluated_at": fixtures.utc_timestamp(6),
    }
    return dict(reference=reference, client_profile=profile, runtime_binding=binding,
                authority_context=context)


def bind_exact_objects(sample):
    """仅按调用方明确要求重绑三对象字节和指纹，不改变任何语义字段。"""
    context, binding = sample["authority_context"], sample["runtime_binding"]
    profile_bytes = fixtures.encode_test_object(sample["client_profile"])
    reference_bytes = fixtures.encode_test_object(sample["reference"])
    binding["trusted_client_profile_fingerprint"] = fixtures.fingerprint(profile_bytes)
    binding["reference_fingerprint"] = fixtures.fingerprint(reference_bytes)
    binding_bytes = fixtures.encode_test_object(binding)
    context["object_bytes"] = {
        "trusted_client_profile": profile_bytes, "registered_context_reference": reference_bytes,
        "runtime_binding": binding_bytes,
    }
    context["control_plane_selection"]["binding_fingerprint"] = fixtures.fingerprint(binding_bytes)


class AuthorityValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = SchemaRegistry()

    def setUp(self):
        self.sample = authority_sample()

    def check(self, sample=None):
        return authority.validate_reference_authority(
            **(self.sample if sample is None else sample), registry=self.registry,
        )

    def assert_positive(self, result, route="runtime_binding", status="authority_context_eligible"):
        self.assertEqual(Decision.PASS, result.decision)
        self.assertEqual(status, result.status)
        self.assertEqual(route, result.record_type)
        self.assertEqual("context-bridge-candidate", result.schema_version)
        self.assertEqual(REFS[route], result.schema_ref)
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

    def test_three_single_object_routes_and_input_immutability(self):
        for name in ("reference", "client_profile", "runtime_binding"):
            record = self.sample[name]
            with self.subTest(route=record["object_kind"]):
                before = copy.deepcopy(record)
                self.assert_positive(authority.validate_authority_object(record, record["object_kind"], self.registry), record["object_kind"], "object_valid")
                self.assertEqual(before, record)

    def test_object_routes_and_schema_failures(self):
        result = authority.validate_authority_object(self.sample["reference"], SENTINELS[2], self.registry)
        self.assert_failure(result, "authority_unsupported_route", "$")
        self.assertIsNone(result.record_type)
        self.assertIsNone(result.schema_ref)
        self.assert_failure(authority.validate_authority_object(self.sample["reference"], "runtime_binding", self.registry), "authority_route_mismatch", "$/object_kind")
        for name, required in (("reference", "reference_id"), ("client_profile", "profile_id"), ("runtime_binding", "binding_id")):
            with self.subTest(object=name):
                record = copy.deepcopy(self.sample[name])
                del record[required]
                record[SENTINELS[1]] = SENTINELS[0]
                self.assert_failure(authority.validate_authority_object(record, record["object_kind"], self.registry), "authority_schema_invalid", "$")

    def test_non_json_and_cyclic_objects(self):
        cyclic = copy.deepcopy(self.sample["client_profile"])
        cyclic["profile_id"] = cyclic
        invalid = copy.deepcopy(self.sample["client_profile"])
        invalid["profile_id"] = b"synthetic bytes"
        for record in (None, [], SENTINELS[0], cyclic, invalid):
            with self.subTest(kind=type(record).__name__):
                self.assert_failure(authority.validate_authority_object(record, "trusted_client_profile", self.registry), "authority_invalid_object")

    def test_registry_and_strict_validation_unavailable(self):
        profile = self.sample["client_profile"]
        with patch.object(authority, "SchemaRegistry", side_effect=RuntimeError(SENTINELS[0])):
            self.assert_failure(authority.validate_authority_object(profile, "trusted_client_profile"), "authority_validation_unavailable", decision=Decision.ERROR, status="validation_unavailable")
        validator = self.registry.validator_for("trusted_client_profile")
        with patch.object(type(validator), "iter_errors", side_effect=RuntimeError(SENTINELS[0])):
            self.assert_failure(authority.validate_authority_object(profile, "trusted_client_profile", self.registry), "authority_validation_unavailable", decision=Decision.ERROR, status="validation_unavailable")

    def test_supplied_context_is_eligible_and_inputs_are_immutable(self):
        before = copy.deepcopy(self.sample)
        self.assertTrue(all(type(blob) is bytes for blob in self.sample["authority_context"]["object_bytes"].values()))
        self.assert_positive(self.check())
        self.assertEqual(before, self.sample)

    def test_wrong_exact_bytes_for_each_object(self):
        for route in REFS:
            with self.subTest(route=route):
                sample = copy.deepcopy(self.sample)
                sample["authority_context"]["object_bytes"][route] = b"{}"
                before = copy.deepcopy(sample)
                self.assert_failure(self.check(sample), "authority_exact_input_mismatch", "$/authority_context/object_bytes/" + route)
                self.assertEqual(before, sample)

    def test_object_bytes_require_native_bytes(self):
        for route in REFS:
            original = self.sample["authority_context"]["object_bytes"][route]
            for value in (original.decode("utf-8"), bytearray(original), {"synthetic_bytes": "not a protocol"}):
                with self.subTest(route=route, kind=type(value).__name__):
                    sample = copy.deepcopy(self.sample)
                    sample["authority_context"]["object_bytes"][route] = value
                    self.assert_failure(self.check(sample), "authority_invalid_object", "$/authority_context/object_bytes/" + route)

    def test_logically_equal_representation_still_binds_exact_fingerprint(self):
        for route in REFS:
            with self.subTest(route=route):
                sample = copy.deepcopy(self.sample)
                sample["authority_context"]["object_bytes"][route] += b"\n"
                result = self.check(sample)
                self.assert_failure(result, "authority_fingerprint_mismatch")
                self.assertNotIn("authority_exact_input_mismatch", {issue.code for issue in result.errors})
        # 空白不是禁止的序列化：显式重绑对应指纹后，原生 JSON bytes 可通过。
        sample = copy.deepcopy(self.sample)
        blobs = sample["authority_context"]["object_bytes"]
        blobs["trusted_client_profile"] += b"\n"
        sample["runtime_binding"]["trusted_client_profile_fingerprint"] = fixtures.fingerprint(blobs["trusted_client_profile"])
        blobs["runtime_binding"] = fixtures.encode_test_object(sample["runtime_binding"]) + b"\n"
        sample["authority_context"]["control_plane_selection"]["binding_fingerprint"] = fixtures.fingerprint(blobs["runtime_binding"])
        self.assert_positive(self.check(sample))

    def test_exact_bytes_reject_malformed_json_bom_and_duplicate_keys(self):
        original = self.sample["authority_context"]["object_bytes"]["runtime_binding"]
        for blob in (b"not JSON", b"\xef\xbb\xbf" + original, b'{"synthetic":1,"synthetic":2}'):
            with self.subTest(blob=blob[:12]):
                sample = copy.deepcopy(self.sample)
                sample["authority_context"]["object_bytes"]["runtime_binding"] = blob
                self.assert_failure(self.check(sample), "authority_exact_input_mismatch")

    def test_identity_linkages(self):
        for field in ("trusted_client_profile_id", "reference_id"):
            with self.subTest(field=field):
                sample = copy.deepcopy(self.sample)
                sample["runtime_binding"][field] = SENTINELS[2]
                bind_exact_objects(sample)
                self.assert_failure(self.check(sample), "authority_identity_mismatch", "$/runtime_binding/" + field)
        self.sample["authority_context"]["control_plane_selection"]["client_id"] = "synthetic_other_client"
        self.assert_failure(self.check(), "authority_identity_mismatch", "$/authority_context/control_plane_selection/client_id")

    def test_fingerprint_linkages(self):
        for field in ("trusted_client_profile_fingerprint", "reference_fingerprint"):
            with self.subTest(field=field):
                sample = copy.deepcopy(self.sample)
                sample["runtime_binding"][field] = fixtures.fingerprint(b"Synthetic P3 other exact bytes")
                blob = fixtures.encode_test_object(sample["runtime_binding"])
                sample["authority_context"]["object_bytes"]["runtime_binding"] = blob
                sample["authority_context"]["control_plane_selection"]["binding_fingerprint"] = fixtures.fingerprint(blob)
                self.assert_failure(self.check(sample), "authority_fingerprint_mismatch", "$/runtime_binding/" + field)
        self.sample["authority_context"]["control_plane_selection"]["binding_fingerprint"] = fixtures.fingerprint(b"Synthetic P3 other binding")
        self.assert_failure(self.check(), "authority_fingerprint_mismatch", "$/authority_context/control_plane_selection/binding_fingerprint")

    def test_non_active_reference_states(self):
        for status in ("paused", "revoked", "archived", "stale_locator", "source_unavailable"):
            with self.subTest(status=status):
                sample = copy.deepcopy(self.sample)
                sample["reference"]["status"] = status
                bind_exact_objects(sample)
                self.assert_failure(self.check(sample), "authority_reference_not_active", "$/reference/status")

    def test_client_must_be_explicitly_allowed(self):
        for clients in ([], ["synthetic_other_client"]):
            with self.subTest(clients=clients):
                sample = copy.deepcopy(self.sample)
                sample["reference"]["allowed_clients"] = clients
                bind_exact_objects(sample)
                self.assert_failure(self.check(sample), "authority_client_not_allowed", "$/reference/allowed_clients")

    def test_revoked_profile_and_structural_revocation_pair(self):
        self.sample["client_profile"].update(profile_status="revoked", revoked_at=fixtures.utc_timestamp(3))
        bind_exact_objects(self.sample)
        self.assert_failure(self.check(), "authority_profile_not_active", "$/client_profile/profile_status")
        for profile_status, revoked_at in (("revoked", None), ("active", fixtures.utc_timestamp(3))):
            with self.subTest(status=profile_status):
                profile = fixtures.load_trusted_client_profile_seed()
                profile["profile_status"] = profile_status
                if revoked_at is not None:
                    profile["revoked_at"] = revoked_at
                self.assert_failure(authority.validate_authority_object(profile, "trusted_client_profile", self.registry), "authority_schema_invalid")

    def test_access_scope_and_transport_match_selection(self):
        self.sample["runtime_binding"]["bound_access_scope"] = "restricted"
        bind_exact_objects(self.sample)
        self.assert_failure(self.check(), "authority_runtime_binding_mismatch", "$/runtime_binding/bound_access_scope")
        for field, value in (("transport_binding_id", SENTINELS[2]), ("transport_class", "stdio")):
            with self.subTest(field=field):
                sample = authority_sample()
                sample["authority_context"]["control_plane_selection"][field] = value
                self.assert_failure(self.check(sample), "authority_runtime_binding_mismatch", "$/authority_context/control_plane_selection/" + field)

    def test_entry_scope_allows_ordered_narrowing_only(self):
        self.sample["runtime_binding"]["bound_entry_points"] = ["synthetic:entry:beta"]
        bind_exact_objects(self.sample)
        self.assert_positive(self.check())
        for entries in (["synthetic:entry:beta", fixtures.SYNTHETIC_ENTRY], ["synthetic:entry:unknown"]):
            with self.subTest(entries=entries):
                sample = authority_sample()
                sample["runtime_binding"]["bound_entry_points"] = entries
                bind_exact_objects(sample)
                self.assert_failure(self.check(sample), "authority_entry_scope_mismatch", "$/runtime_binding/bound_entry_points")

    def test_frozen_operation_vocabulary(self):
        for operation in ("get_reference", "resolve_context"):
            with self.subTest(operation=operation):
                sample = copy.deepcopy(self.sample)
                sample["authority_context"]["operation"] = operation
                self.assert_positive(self.check(sample))
                sample["runtime_binding"]["allowed_operations"] = ["get_reference" if operation == "resolve_context" else "resolve_context"]
                bind_exact_objects(sample)
                self.assert_failure(self.check(sample), "authority_operation_not_allowed", "$/authority_context/operation")
        self.sample["authority_context"]["operation"] = "synthetic_invalid_operation"
        self.assert_failure(self.check(), "authority_invalid_object", "$/authority_context/operation")

    def test_expiry_at_explicit_evaluation_boundary(self):
        for expires, eligible in ((7, True), (6, False), (5, False)):
            with self.subTest(expires=expires):
                sample = copy.deepcopy(self.sample)
                sample["client_profile"]["expires_at"] = fixtures.utc_timestamp(expires)
                bind_exact_objects(sample)
                result = self.check(sample)
                if eligible:
                    self.assert_positive(result)
                else:
                    self.assert_failure(result, "authority_profile_expired", "$/client_profile/expires_at")

    def test_explicit_timestamp_ordering(self):
        for name, field, seconds in (
            ("client_profile", "created_at", 6), ("reference", "registered_at", 6),
            ("runtime_binding", "created_at", 7), ("authority_context", "evaluated_at", 4),
            ("client_profile", "expires_at", -1),
        ):
            with self.subTest(object=name, field=field):
                sample = copy.deepcopy(self.sample)
                sample[name][field] = fixtures.utc_timestamp(seconds)
                bind_exact_objects(sample)
                self.assert_failure(self.check(sample), "authority_timestamp_inconsistent")
        for revoked in (-1, 7):
            with self.subTest(revoked=revoked):
                sample = copy.deepcopy(self.sample)
                sample["client_profile"].update(profile_status="revoked", revoked_at=fixtures.utc_timestamp(revoked))
                bind_exact_objects(sample)
                self.assert_failure(self.check(sample), "authority_timestamp_inconsistent")
        self.sample["authority_context"]["evaluated_at"] = "synthetic_invalid_timestamp"
        self.assert_failure(self.check(), "authority_invalid_object", "$/authority_context/evaluated_at")

    def test_missing_authority_context_and_all_object_bytes(self):
        for field in ("object_bytes", "control_plane_selection", "operation", "evaluated_at"):
            with self.subTest(field=field):
                sample = copy.deepcopy(self.sample)
                del sample["authority_context"][field]
                self.assert_failure(self.check(sample), "authority_context_missing", decision=Decision.NEEDS_REVIEW, status="incomplete_authority_context")
        for route in REFS:
            with self.subTest(route=route):
                sample = copy.deepcopy(self.sample)
                del sample["authority_context"]["object_bytes"][route]
                self.assert_failure(self.check(sample), "authority_context_missing", "$/authority_context/object_bytes/" + route, Decision.NEEDS_REVIEW, "incomplete_authority_context")
        self.sample["authority_context"] = None
        self.assert_failure(self.check(), "authority_context_missing", decision=Decision.NEEDS_REVIEW, status="incomplete_authority_context")

    def test_priority_reject_over_missing_context(self):
        self.sample["reference"]["status"] = "paused"
        bind_exact_objects(self.sample)
        del self.sample["authority_context"]["operation"]
        result = self.check()
        self.assert_failure(result, "authority_reference_not_active")
        self.assertIn("authority_context_missing", {issue.code for issue in result.errors})

    def test_priority_reject_over_real_strict_unavailability(self):
        # Reference 的 route 矛盾先成立；另两对象实际调用的 Registry 随后失败。
        self.sample["reference"]["object_kind"] = "synthetic_wrong_route"
        with patch.object(self.registry, "validator_for", side_effect=RuntimeError(SENTINELS[0])) as strict:
            result = self.check()
        self.assertTrue(strict.called)
        self.assert_failure(result, "authority_route_mismatch")
        self.assertIn("authority_validation_unavailable", {issue.code for issue in result.errors})

    def test_priority_error_over_missing_context(self):
        del self.sample["authority_context"]["operation"]
        with patch.object(self.registry, "validator_for", side_effect=RuntimeError(SENTINELS[0])) as strict:
            result = self.check()
        self.assertTrue(strict.called)
        self.assert_failure(result, "authority_validation_unavailable", decision=Decision.ERROR, status="validation_unavailable")
        self.assertIn("authority_context_missing", {issue.code for issue in result.errors})

    def test_supplied_registry_reaches_object_exact_and_time_checks(self):
        with patch.object(authority, "SchemaRegistry", side_effect=AssertionError("unexpected registry")) as factory, patch.object(self.registry, "validator_for", wraps=self.registry.validator_for) as strict:
            self.assert_positive(self.check())
            for name in ("reference", "client_profile", "runtime_binding"):
                record = self.sample[name]
                self.assert_positive(authority.validate_authority_object(record, record["object_kind"], self.registry), record["object_kind"], "object_valid")
            self.sample["authority_context"]["object_bytes"]["runtime_binding"] = b"{}"
            self.assert_failure(self.check(), "authority_exact_input_mismatch")
            self.sample["authority_context"]["evaluated_at"] = "synthetic_invalid_timestamp"
            self.assert_failure(self.check(), "authority_invalid_object")
        factory.assert_not_called()
        self.assertEqual(set(REFS), {item.args[0] for item in strict.call_args_list})

    def test_diagnostics_do_not_echo_private_values_or_exceptions(self):
        for field, value in (("canonical_name", SENTINELS[0]), ("source_locator", SENTINELS[1]), ("reference_id", SENTINELS[2])):
            with self.subTest(field=field):
                sample = copy.deepcopy(self.sample)
                sample["reference"][field] = value
                self.assert_failure(self.check(sample), "authority_exact_input_mismatch")
        with patch.object(self.registry, "validator_for", side_effect=RuntimeError(" ".join(SENTINELS))):
            self.assert_failure(self.check(), "authority_validation_unavailable", decision=Decision.ERROR, status="validation_unavailable")

    def test_safe_timestamp_resource_ceiling(self):
        # 257 字符刚好越过冻结的 256 字符私有预算，不分配大块内存。
        self.sample["authority_context"]["evaluated_at"] = "2" * 257
        self.assert_failure(self.check(), "authority_resource_limit_exceeded", "$/authority_context/evaluated_at", Decision.ERROR, "validation_unavailable")
        profile = fixtures.load_trusted_client_profile_seed()
        profile["created_at"] = "2" * 257
        self.assert_failure(authority.validate_authority_object(profile, "trusted_client_profile", self.registry), "authority_resource_limit_exceeded", "$/created_at", Decision.ERROR, "validation_unavailable")


if __name__ == "__main__":
    unittest.main()
