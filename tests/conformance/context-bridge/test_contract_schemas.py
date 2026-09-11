"""冻结候选 Schema 的结构证据；不判断 P2 运行时语义或真实授权。

样本完全合成。预期路线在测试侧独立写死；所有接受/拒绝断言均经过项目的
真实严格 SchemaRegistry（模式注册表），不在此实现业务验证器。
"""

import copy
import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from xingshu_core.schema_registry import CONTEXT_BRIDGE_SCHEMA_REFS, SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests/support"))
import context_bridge_fixtures as fixtures  # noqa: E402


EXPECTED_ROUTES = {
    "context_candidate": "schemas/candidate/context-bridge/context-candidate.schema.json",
    "context_registration_proposal": "schemas/candidate/context-bridge/context-registration-proposal.schema.json",
    "context_validation_artifact": "schemas/candidate/context-bridge/context-validation-artifact.schema.json",
    "human_authorization_evidence": "schemas/candidate/context-bridge/human-authorization-evidence.schema.json",
    "registered_context_reference": "schemas/candidate/context-bridge/registered-context-reference.schema.json",
    "context_reference_transition": "schemas/candidate/context-bridge/context-reference-transition.schema.json",
    "source_adapter_manifest": "schemas/candidate/context-bridge/source-adapter-contract.schema.json",
    "source_adapter_request": "schemas/candidate/context-bridge/source-adapter-contract.schema.json",
    "source_adapter_result": "schemas/candidate/context-bridge/source-adapter-contract.schema.json",
    "source_adapter_error": "schemas/candidate/context-bridge/source-adapter-contract.schema.json",
    "trusted_client_profile": "schemas/candidate/context-bridge/trusted-client-profile.schema.json",
    "runtime_binding": "schemas/candidate/context-bridge/runtime-binding.schema.json",
    "resolve_context_request": "schemas/candidate/context-bridge/resolve-context.schema.json",
    "resolve_context_result": "schemas/candidate/context-bridge/resolve-context.schema.json",
    "resolve_context_error": "schemas/candidate/context-bridge/resolve-context.schema.json",
    "derived_provider_metadata": "schemas/candidate/context-bridge/derived-provider-metadata.schema.json",
}
SEED_LOADERS = {
    "context-candidate-valid.json": fixtures.load_context_candidate_seed,
    "source-adapter-manifest-valid.json": fixtures.load_source_adapter_manifest_seed,
    "trusted-client-profile-valid.json": fixtures.load_trusted_client_profile_seed,
    "derived-provider-metadata-valid.json": fixtures.load_derived_provider_metadata_seed,
}
DELETE = object()


def positive_objects():
    """显式依赖顺序；仅组织结构样本，不调用任何跨证据验证接口。"""
    candidate = fixtures.load_context_candidate_seed()
    candidate_bytes = (fixtures.FIXTURE_ROOT / "context-candidate-valid.json").read_bytes()
    proposal = fixtures.build_registration_proposal(candidate, candidate_bytes=candidate_bytes)
    manifest = fixtures.load_source_adapter_manifest_seed()
    source_request = fixtures.build_source_adapter_request(manifest)
    source_result = fixtures.build_source_adapter_result(source_request)
    validation = fixtures.build_context_validation_artifact(
        candidate, proposal, candidate_bytes=candidate_bytes,
        proposal_bytes=fixtures.encode_test_object(proposal),
        review_evidence_bytes=b"Synthetic P3 untrusted review evidence",
        snapshot_bytes=b"Synthetic P3 empty reference snapshot",
        source_observation_bytes=[fixtures.encode_test_object(source_result)],
    )
    authorization = fixtures.build_human_authorization_evidence(
        candidate, proposal, validation, validation_bytes=fixtures.encode_test_object(validation),
    )
    reference = fixtures.build_registered_context_reference(authorization)
    reference_bytes = fixtures.encode_test_object(reference)
    paused_reference = copy.deepcopy(reference)
    paused_reference["status"] = "paused"
    transition = fixtures.build_context_reference_transition(
        reference, paused_reference, previous_bytes=reference_bytes,
        new_bytes=fixtures.encode_test_object(paused_reference),
    )
    profile = fixtures.load_trusted_client_profile_seed()
    binding = fixtures.build_runtime_binding(
        profile, reference, profile_bytes=fixtures.encode_test_object(profile),
        reference_bytes=reference_bytes,
    )
    resolve_request = fixtures.build_resolve_context_request(reference)
    resolve_result = fixtures.build_resolve_context_result(
        resolve_request, reference, binding, source_result, reference_bytes=reference_bytes,
        exact_content_bytes=source_result["payload"]["text"].encode("utf-8"),
    )
    return {
        "context_candidate": candidate,
        "context_registration_proposal": proposal,
        "context_validation_artifact": validation,
        "human_authorization_evidence": authorization,
        "registered_context_reference": reference,
        "context_reference_transition": transition,
        "source_adapter_manifest": manifest,
        "source_adapter_request": source_request,
        "source_adapter_result": source_result,
        "source_adapter_error": fixtures.build_source_adapter_error(source_request),
        "trusted_client_profile": profile,
        "runtime_binding": binding,
        "resolve_context_request": resolve_request,
        "resolve_context_result": resolve_result,
        "resolve_context_error": fixtures.build_resolve_context_error(resolve_request),
        "derived_provider_metadata": fixtures.load_derived_provider_metadata_seed(),
    }


class ContextBridgeSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = SchemaRegistry()
        cls.validators = {route: cls.registry.validator_for(route) for route in EXPECTED_ROUTES}
        cls.positives = positive_objects()
        # 反例只从已经通过真实严格验证的正向对象产生。
        for route, record in cls.positives.items():
            cls.validators[route].validate(record)

    def assert_schema_valid(self, route, record):
        self.assertEqual([], list(self.validators[route].iter_errors(record)))

    def assert_schema_invalid(self, route, record):
        self.assertTrue(list(self.validators[route].iter_errors(record)))

    def reject_mutation(self, route, path, value, base=None):
        original = self.positives[route] if base is None else base
        self.assert_schema_valid(route, original)
        record = copy.deepcopy(original)
        parent = record
        for key in path[:-1]:
            parent = parent[key]
        if value is DELETE:
            del parent[path[-1]]
        else:
            parent[path[-1]] = copy.deepcopy(value)
        self.assert_schema_invalid(route, record)

    def test_exact_internal_inventory_and_schema_paths(self):
        self.assertEqual(16, len(EXPECTED_ROUTES))
        self.assertEqual(11, len(set(EXPECTED_ROUTES.values())))
        self.assertEqual(EXPECTED_ROUTES, CONTEXT_BRIDGE_SCHEMA_REFS)
        self.assertEqual(tuple(EXPECTED_ROUTES), self.registry.supported_context_bridge_record_types)
        self.assertEqual(EXPECTED_ROUTES, self.registry.discover_context_bridge())
        actual_paths = {str(p.relative_to(ROOT)) for p in (ROOT / "schemas/candidate/context-bridge").glob("*.schema.json")}
        self.assertEqual(set(EXPECTED_ROUTES.values()), actual_paths)
        for route, ref in EXPECTED_ROUTES.items():
            with self.subTest(route=route):
                path = self.registry.schema_path_for(route)
                self.assertEqual((ROOT / ref).resolve(), path)
                self.assertIn(self.registry.schema_root, path.parents)
                self.assertEqual(ref, self.registry.schema_ref_for(route))
        legacy = self.registry.discover()
        self.assertNotEqual(EXPECTED_ROUTES, legacy)
        self.assertTrue(set(legacy).isdisjoint(EXPECTED_ROUTES))

    def test_all_sixteen_objects_use_real_strict_validators(self):
        self.assertEqual(set(EXPECTED_ROUTES), set(self.positives))
        for route, record in self.positives.items():
            with self.subTest(route=route):
                validator = self.validators[route]
                self.assertIsInstance(validator, Draft202012Validator)
                self.assertIsNotNone(validator.format_checker)
                self.assertEqual("https://json-schema.org/draft/2020-12/schema", validator.schema["$schema"])
                self.assertEqual(route, record["object_kind"])
                self.assert_schema_valid(route, record)

    def test_shared_schemas_cover_each_discriminated_envelope(self):
        families = (
            ("source-adapter-contract.schema.json", ("source_adapter_manifest", "source_adapter_request", "source_adapter_result", "source_adapter_error")),
            ("resolve-context.schema.json", ("resolve_context_request", "resolve_context_result", "resolve_context_error")),
        )
        for filename, routes in families:
            for route in routes:
                with self.subTest(route=route):
                    self.assertEqual("schemas/candidate/context-bridge/" + filename, self.registry.schema_ref_for(route))
                    self.assert_schema_valid(route, self.positives[route])
        self.assertIn("resolve_context_error", self.registry.discover_context_bridge())

    def test_exact_four_strict_json_seeds(self):
        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate seed key")
                result[key] = value
            return result

        def invalid_constant(value):
            raise ValueError("non-JSON numeric constant")

        self.assertEqual(set(SEED_LOADERS), {p.name for p in fixtures.FIXTURE_ROOT.iterdir()})
        for filename, load in SEED_LOADERS.items():
            with self.subTest(seed=filename):
                raw = (fixtures.FIXTURE_ROOT / filename).read_bytes()
                parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs, parse_constant=invalid_constant)
                self.assertEqual(parsed, load())
                self.assert_schema_valid(parsed["object_kind"], parsed)
        # unverified 种子的指纹来自下列明确合成标签字节，不冒充真实关联证据。
        derived = fixtures.load_derived_provider_metadata_seed()
        self.assertEqual(fixtures.fingerprint(b"synthetic:p3:reference:01"), derived["authoritative_reference_fingerprint"])
        self.assertEqual([fixtures.fingerprint(b"synthetic:p3:observation:01")], derived["provenance"]["source_observation_fingerprints"])

    def test_common_root_structure_rejections(self):
        mutations = (
            (("synthetic_unexpected",), True),
            (("schema_version",), "synthetic-unsupported-version"),
            (("object_kind",), "synthetic_unsupported_kind"),
            (("object_kind",), DELETE),
            (("schema_version",), 1),
        )
        for route in EXPECTED_ROUTES:
            for path, value in mutations:
                with self.subTest(route=route, path=path, value=value):
                    self.reject_mutation(route, path, value)

    def test_nested_closed_objects(self):
        paths = (
            ("source_adapter_manifest", ("hard_limits",)),
            ("source_adapter_request", ("requested_limits",)),
            ("source_adapter_result", ("payload",)),
            ("source_adapter_result", ("provenance",)),
            ("source_adapter_result", ("applied_limits",)),
            ("resolve_context_request", ("requested_limits",)),
            ("resolve_context_result", ("freshness",)),
            ("resolve_context_result", ("payload", 0)),
            ("resolve_context_result", ("provenance",)),
            ("resolve_context_result", ("applied_limits",)),
            ("derived_provider_metadata", ("provenance",)),
            ("derived_provider_metadata", ("fallback_policy",)),
        )
        for route, path in paths:
            with self.subTest(route=route, path=path):
                self.reject_mutation(route, path + ("synthetic_unexpected",), True)

    def test_closed_enums_and_fixed_claims(self):
        rows = (
            ("context_candidate", "context_type", "synthetic_unknown"),
            ("context_registration_proposal", "suggested_access_scope", "synthetic_unknown"),
            ("context_validation_artifact", "validation_outcome", "error"),
            ("human_authorization_evidence", "user_authorized", False),
            ("human_authorization_evidence", "authorization_method", "synthetic_automatic"),
            ("registered_context_reference", "status", "candidate"),
            ("source_adapter_request", "operation", "write"),
            ("source_adapter_error", "error_code", "synthetic_unknown"),
            ("source_adapter_manifest", "binary_supported", True),
            ("trusted_client_profile", "identity_origin", "synthetic_self_report"),
            ("runtime_binding", "transport_class", "synthetic_unknown"),
            ("resolve_context_error", "error_code", "synthetic_unknown"),
            ("resolve_context_result", "payload_persistence", "permanent"),
            ("derived_provider_metadata", "final_authority", True),
            ("derived_provider_metadata", "rebuildable", False),
        )
        for route, field, value in rows:
            with self.subTest(route=route, field=field):
                self.reject_mutation(route, (field,), value)

    def test_primitive_types_and_array_bounds(self):
        rows = (
            ("context_candidate", ("source_id",), 1),
            ("source_adapter_manifest", ("hard_limits", "max_items"), True),
            ("source_adapter_request", ("requested_limits", "max_bytes"), "1024"),
            ("source_adapter_request", ("requested_limits", "max_items"), 0),
            ("source_adapter_result", ("payload", "byte_count"), 1.5),
            ("source_adapter_error", ("retryable",), "true"),
            ("trusted_client_profile", ("profile_version",), True),
            ("runtime_binding", ("bound_entry_points",), []),
            ("runtime_binding", ("allowed_operations",), ["write"]),
            ("runtime_binding", ("allowed_operations",), ["resolve_context", "resolve_context"]),
            ("resolve_context_request", ("requested_limits", "max_items"), 129),
            ("resolve_context_result", ("payload",), []),
            ("resolve_context_result", ("minimum_disclosure",), "true"),
            ("context_registration_proposal", ("suggested_source_entry_points",), ["synthetic:entry:alpha"] * 2),
            ("context_registration_proposal", ("suggested_source_entry_points",), [f"synthetic:entry:{i}" for i in range(9)]),
        )
        for route, path, value in rows:
            with self.subTest(route=route, path=path, value=value):
                self.reject_mutation(route, path, value)

    def test_fingerprint_shapes(self):
        fields = (
            ("context_registration_proposal", ("candidate_fingerprint",)),
            ("context_validation_artifact", ("source_observation_fingerprints", 0)),
            ("human_authorization_evidence", ("validation_artifact_fingerprint",)),
            ("context_reference_transition", ("previous_reference_fingerprint",)),
            ("runtime_binding", ("trusted_client_profile_fingerprint",)),
            ("source_adapter_result", ("provenance", "content_fingerprint")),
            ("resolve_context_result", ("payload", 0, "content_fingerprint")),
            ("derived_provider_metadata", ("authoritative_reference_fingerprint",)),
        )
        for route, path in fields:
            for value in ("sha256:abc", "sha256:" + "A" * 64, "md5:" + "a" * 64):
                with self.subTest(route=route, path=path, value=value):
                    self.reject_mutation(route, path, value)

    def test_real_datetime_format_checking(self):
        fields = (
            ("context_candidate", ("last_verified_at",)),
            ("context_registration_proposal", ("last_verified_at",)),
            ("context_validation_artifact", ("validated_at",)),
            ("human_authorization_evidence", ("authorized_at",)),
            ("registered_context_reference", ("registered_at",)),
            ("context_reference_transition", ("transitioned_at",)),
            ("source_adapter_result", ("provenance", "observed_at")),
            ("source_adapter_error", ("observed_at",)),
            ("trusted_client_profile", ("created_at",)),
            ("runtime_binding", ("created_at",)),
            ("resolve_context_result", ("freshness", "verified_at")),
            ("resolve_context_error", ("observed_at",)),
            ("derived_provider_metadata", ("created_at",)),
        )
        for route, path in fields:
            for value in ("not-a-date", "2026-02-30T00:00:00Z", "2026-01-01T00:00:00"):
                with self.subTest(route=route, path=path, value=value):
                    self.reject_mutation(route, path, value)
            record = copy.deepcopy(self.positives[route])
            parent = record
            for key in path[:-1]:
                parent = parent[key]
            parent[path[-1]] = "2026-01-01T08:00:00+08:00"
            self.assert_schema_valid(route, record)

    def test_verification_pair_branches(self):
        for route in ("context_candidate", "context_registration_proposal", "registered_context_reference"):
            for mode in ("absent", "null"):
                with self.subTest(route=route, positive=mode):
                    record = copy.deepcopy(self.positives[route])
                    for field in ("last_verified_at", "verification_evidence_id"):
                        if mode == "absent":
                            del record[field]
                        else:
                            record[field] = None
                    self.assert_schema_valid(route, record)
            for field in ("last_verified_at", "verification_evidence_id"):
                for value in (DELETE, None):
                    with self.subTest(route=route, field=field, value=value):
                        self.reject_mutation(route, (field,), value)

    def test_validation_outcome_issue_conditions(self):
        route = "context_validation_artifact"
        self.reject_mutation(route, ("issue_codes",), ["synthetic_issue"])
        for outcome in ("needs_review", "reject"):
            with self.subTest(outcome=outcome):
                self.reject_mutation(route, ("validation_outcome",), outcome)
                record = copy.deepcopy(self.positives[route])
                record.update(validation_outcome=outcome, issue_codes=["synthetic_issue"])
                self.assert_schema_valid(route, record)
        # 此数组明确允许重复，不把其他数组的 uniqueItems 语义复制过来。
        record = copy.deepcopy(self.positives[route])
        record["source_observation_fingerprints"] *= 2
        self.assert_schema_valid(route, record)

    def test_human_projection_and_binding_required_fields(self):
        required = {
            "human_authorization_evidence": (
                "authorization_method", "context_type", "source_id", "initial_status", "retrieval_hint",
                "final_canonical_name", "final_source_locator", "final_source_entry_points",
                "final_access_scope", "final_allowed_clients", "final_freshness_policy", "final_provenance_policy",
            ),
            "runtime_binding": (
                "trusted_client_profile_id", "trusted_client_profile_fingerprint", "reference_id",
                "reference_fingerprint", "bound_access_scope", "bound_entry_points", "allowed_operations",
                "transport_binding_id", "transport_class",
            ),
            "context_reference_transition": ("reference_id", "previous_reference_fingerprint", "new_reference_fingerprint", "from_status", "to_status", "transitioned_at"),
        }
        for route, fields in required.items():
            for field in fields:
                with self.subTest(route=route, field=field):
                    self.reject_mutation(route, (field,), DELETE)

    def test_client_arrays_preserve_deny_all_and_reject_wildcards(self):
        rows = (
            ("context_registration_proposal", "suggested_allowed_clients"),
            ("human_authorization_evidence", "final_allowed_clients"),
            ("registered_context_reference", "allowed_clients"),
        )
        for route, field in rows:
            with self.subTest(route=route):
                record = copy.deepcopy(self.positives[route])
                record[field] = []
                self.assert_schema_valid(route, record)
                self.reject_mutation(route, (field,), ["*"])

    def test_reference_fingerprint_policy_condition(self):
        route = "registered_context_reference"
        self.reject_mutation(route, ("provenance_policy",), "locator_and_fingerprint")
        record = copy.deepcopy(self.positives[route])
        record["provenance_policy"] = "locator_and_fingerprint"
        record["content_fingerprint"] = fixtures.fingerprint(b"Synthetic P3 content")
        self.assert_schema_valid(route, record)
        self.reject_mutation(route, ("content_fingerprint",), "sha256:abc", record)

    def test_transition_schema_graph(self):
        # 此有限状态对表只作为 Schema 预期；不判断跨对象一致性或执行权限。
        allowed = {
            "active": {"paused", "source_unavailable", "stale_locator", "revoked", "archived"},
            "paused": {"active", "source_unavailable", "stale_locator", "revoked", "archived"},
            "source_unavailable": {"active", "paused", "stale_locator", "revoked", "archived"},
            "stale_locator": {"paused", "revoked", "archived"},
            "revoked": {"archived"},
            "archived": set(),
        }
        for before, targets in allowed.items():
            for after in allowed:
                with self.subTest(before=before, after=after):
                    record = copy.deepcopy(self.positives["context_reference_transition"])
                    record.update(from_status=before, to_status=after)
                    self.assertEqual(after in targets, self.validators["context_reference_transition"].is_valid(record))

    def test_profile_revocation_condition(self):
        route = "trusted_client_profile"
        self.reject_mutation(route, ("profile_status",), "revoked")
        self.reject_mutation(route, ("revoked_at",), fixtures.utc_timestamp(8))
        record = copy.deepcopy(self.positives[route])
        record.update(profile_status="revoked", revoked_at=fixtures.utc_timestamp(8))
        self.assert_schema_valid(route, record)

    def test_source_operation_payload_branches(self):
        for operation in ("capabilities", "list", "stat", "read"):
            with self.subTest(operation=operation):
                request = copy.deepcopy(self.positives["source_adapter_request"])
                request["operation"] = operation
                if operation == "capabilities":
                    del request["target_locator"]
                    self.assert_schema_valid("source_adapter_request", request)
                    self.reject_mutation("source_adapter_request", ("target_locator",), fixtures.SYNTHETIC_ENTRY, request)
                else:
                    self.assert_schema_valid("source_adapter_request", request)
                    self.reject_mutation("source_adapter_request", ("target_locator",), DELETE, request)
                result = copy.deepcopy(self.positives["source_adapter_result"])
                result["operation"] = operation
                result["provenance"]["operation"] = operation
                payloads = {
                    "capabilities": {"payload_kind": "capabilities", "operations": ["read"]},
                    "list": {"payload_kind": "list", "items": [{"locator": fixtures.SYNTHETIC_ENTRY, "item_type": "text"}]},
                    "stat": {"payload_kind": "stat", "locator": fixtures.SYNTHETIC_ENTRY, "item_type": "text", "byte_count": 1},
                    "read": result["payload"],
                }
                result["payload"] = payloads[operation]
                self.assert_schema_valid("source_adapter_result", result)
                other = "list" if operation != "list" else "stat"
                self.reject_mutation("source_adapter_result", ("payload",), payloads[other], result)

    def test_success_error_envelopes_do_not_mix(self):
        for error_route, result_route in (
            ("source_adapter_error", "source_adapter_result"),
            ("resolve_context_error", "resolve_context_result"),
        ):
            with self.subTest(error=error_route):
                self.reject_mutation(error_route, ("payload",), self.positives[result_route]["payload"])
                self.reject_mutation(result_route, ("error_code",), "source_unavailable")
                self.reject_mutation(error_route, ("object_kind",), result_route)
                self.reject_mutation(result_route, ("object_kind",), error_route)
        self.reject_mutation("source_adapter_result", ("ok",), False)

    def test_derived_metadata_conditions(self):
        route = "derived_provider_metadata"
        self.reject_mutation(route, ("verification_state",), "authoritatively_supported")
        supported = copy.deepcopy(self.positives[route])
        supported.update(verification_state="authoritatively_supported", freshness_state="current")
        self.assert_schema_valid(route, supported)
        self.reject_mutation(route, ("usable_for_lookup",), True, supported)
        supported.update(usable_for_lookup=True, derived_hint={"hint_type": "entry_selection", "hint_values": [fixtures.SYNTHETIC_ENTRY]})
        self.assert_schema_valid(route, supported)
        for state in ("unverified", "unsupported", "stale"):
            with self.subTest(state=state):
                self.reject_mutation(route, ("verification_state",), state, supported)
        self.reject_mutation(route, ("derived_hint", "hint_values"), ["*"], supported)
        self.reject_mutation(route, ("derived_hint", "synthetic_unexpected"), True, supported)

    def test_test_only_bytes_have_independent_fixed_vectors(self):
        left = {"z": "合成\n", "a": [1, True]}
        right = {"a": [1, True], "z": "合成\n"}
        expected = '{"a":[1,true],"z":"合成\\n"}'.encode("utf-8")
        original = copy.deepcopy(left)
        self.assertEqual(expected, fixtures.encode_test_object(left))
        self.assertEqual(expected, fixtures.encode_test_object(right))
        self.assertEqual(original, left)
        self.assertIs(type(fixtures.encode_test_object(left)), bytes)
        self.assertEqual("sha256:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", fixtures.fingerprint(b"abc"))
        self.assertNotEqual(fixtures.fingerprint(b"abc"), fixtures.fingerprint(b"abc\n"))
        self.assertGreater(len(fixtures.SYNTHETIC_TEXT.encode("utf-8")), len(fixtures.SYNTHETIC_TEXT))
        self.assertEqual("2026-01-01T00:00:00Z", fixtures.utc_timestamp())
        self.assertEqual("2026-01-02T00:00:00Z", fixtures.utc_timestamp(86400))
        with self.assertRaises(ValueError):
            fixtures.encode_test_object({"synthetic_number": float("nan")})

    def test_builders_do_not_share_or_repair_mutations(self):
        first, second = positive_objects(), positive_objects()
        self.assertEqual(first, second)
        proposal = first["context_registration_proposal"]
        original_fingerprint = proposal["candidate_fingerprint"]
        candidate = first["context_candidate"]
        candidate["discovered_name"] = "Synthetic P3 changed name"
        self.assertEqual(original_fingerprint, proposal["candidate_fingerprint"])
        rebuilt = fixtures.build_registration_proposal(candidate, candidate_bytes=fixtures.encode_test_object(candidate))
        self.assertNotEqual(original_fingerprint, rebuilt["candidate_fingerprint"])
        supplied = fixtures.build_registration_proposal(candidate, candidate_bytes=b"Synthetic P3 explicitly supplied bytes")
        self.assertEqual(fixtures.fingerprint(b"Synthetic P3 explicitly supplied bytes"), supplied["candidate_fingerprint"])
        proposal["suggested_source_entry_points"].append("synthetic:entry:beta")
        self.assertEqual([fixtures.SYNTHETIC_ENTRY], first["human_authorization_evidence"]["final_source_entry_points"])
        first["registered_context_reference"]["source_entry_points"].append("synthetic:entry:gamma")
        self.assertEqual([fixtures.SYNTHETIC_ENTRY], first["runtime_binding"]["bound_entry_points"])
        first["source_adapter_result"]["payload"]["text"] = "Synthetic P3 changed text"
        self.assertEqual(fixtures.SYNTHETIC_TEXT, first["resolve_context_result"]["payload"][0]["text"])
        self.assertEqual(second, positive_objects())


if __name__ == "__main__":
    unittest.main()
