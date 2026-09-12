"""P2B 合成跨证据回归；通过只表示声明自洽，不认证真人或启动运行时。"""

import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from xingshu_core import context_bridge_validation as bridge
from xingshu_core import source_adapter_validation as source
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
    "context_candidate": "schemas/candidate/context-bridge/context-candidate.schema.json",
    "context_registration_proposal": "schemas/candidate/context-bridge/context-registration-proposal.schema.json",
    "context_validation_artifact": "schemas/candidate/context-bridge/context-validation-artifact.schema.json",
    "human_authorization_evidence": "schemas/candidate/context-bridge/human-authorization-evidence.schema.json",
    "registered_context_reference": "schemas/candidate/context-bridge/registered-context-reference.schema.json",
    "context_reference_transition": "schemas/candidate/context-bridge/context-reference-transition.schema.json",
}


def registration_sample():
    """复用 P3A 构造器，显式装配证据；不实现验证或自动修复变异。"""
    candidate = fixtures.load_context_candidate_seed()
    candidate_bytes = (fixtures.FIXTURE_ROOT / "context-candidate-valid.json").read_bytes()
    proposal = fixtures.build_registration_proposal(candidate, candidate_bytes=candidate_bytes)
    proposal_bytes = fixtures.encode_test_object(proposal)
    manifest = fixtures.load_source_adapter_manifest_seed()
    request = fixtures.build_source_adapter_request(manifest)
    response = fixtures.build_source_adapter_result(request)
    response_bytes = fixtures.encode_test_object(response)
    review_bytes = b"Synthetic P3 untrusted review evidence"
    policy_bytes = b"Synthetic P3 identified validation policy"
    snapshot_bytes = b"Synthetic P3 empty reference snapshot"
    validation = fixtures.build_context_validation_artifact(
        candidate, proposal, candidate_bytes=candidate_bytes, proposal_bytes=proposal_bytes,
        review_evidence_bytes=review_bytes, snapshot_bytes=snapshot_bytes,
        source_observation_bytes=[response_bytes],
    )
    validation_bytes = fixtures.encode_test_object(validation)
    authorization = fixtures.build_human_authorization_evidence(
        candidate, proposal, validation, validation_bytes=validation_bytes,
    )
    reference = fixtures.build_registered_context_reference(authorization)
    context = {
        "object_bytes": {"candidate": candidate_bytes, "proposal": proposal_bytes, "validation_artifact": validation_bytes},
        "review_evidence_bytes": review_bytes,
        "policy": {
            "policy_id": validation["validation_policy_id"],
            "policy_version": validation["validation_policy_version"],
            "policy_bytes": policy_bytes, "expected_policy_fingerprint": fixtures.fingerprint(policy_bytes),
        },
        "existing_snapshot": {
            "snapshot_bytes": snapshot_bytes,
            "id_index": {"snapshot_fingerprint": fixtures.fingerprint(snapshot_bytes), "reference_ids": []},
        },
        "source_observations": [{
            "entry_index": 0, "evidence_bytes": response_bytes, "manifest": manifest,
            "request": request, "response": response, "expected_scope_id": request["scope_id"],
            "exact_content_bytes": response["payload"]["text"].encode("utf-8"),
        }],
    }
    return dict(candidate=candidate, proposal=proposal, validation_artifact=validation,
                authorization=authorization, reference=reference, evidence_context=context)


def transition_sample(reference):
    previous, new = copy.deepcopy(reference), copy.deepcopy(reference)
    new["status"] = "paused"
    previous_bytes, new_bytes = fixtures.encode_test_object(previous), fixtures.encode_test_object(new)
    event = fixtures.build_context_reference_transition(
        previous, new, previous_bytes=previous_bytes, new_bytes=new_bytes,
    )
    return dict(previous_reference=previous, new_reference=new, transition=event,
                evidence_context={"object_bytes": {"previous_reference": previous_bytes, "new_reference": new_bytes}})


class ContextBridgeValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = SchemaRegistry()

    def setUp(self):
        self.sample = registration_sample()

    def validation(self, sample=None):
        sample = self.sample if sample is None else sample
        return bridge.validate_registration_validation(
            sample["candidate"], sample["proposal"], sample["validation_artifact"],
            evidence_context=sample["evidence_context"], registry=self.registry,
        )

    def chain(self, sample=None):
        return bridge.validate_registration_chain(**(self.sample if sample is None else sample), registry=self.registry)

    def assert_positive(self, result, route, status):
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
        self.assertTrue(all(issue.field is None for issue in result.errors))

    def test_six_single_objects_have_exact_positive_results(self):
        objects = [self.sample[key] for key in ("candidate", "proposal", "validation_artifact", "authorization", "reference")]
        objects.append(transition_sample(self.sample["reference"])["transition"])
        self.assertEqual(set(REFS), {record["object_kind"] for record in objects})
        for record in objects:
            with self.subTest(route=record["object_kind"]):
                before = copy.deepcopy(record)
                self.assert_positive(bridge.validate_context_bridge_object(record, record["object_kind"], self.registry), record["object_kind"], "object_valid")
                self.assertEqual(before, record)

    def test_single_object_route_schema_and_unavailable_failures(self):
        self.assert_failure(bridge.validate_context_bridge_object(self.sample["candidate"], "human_authorization_evidence", self.registry), "context_bridge_route_mismatch", "$/object_kind")
        result = bridge.validate_context_bridge_object(self.sample["candidate"], SENTINELS[2], self.registry)
        self.assert_failure(result, "context_bridge_unsupported_route", "$")
        self.assertIsNone(result.record_type)
        self.assertIsNone(result.schema_ref)
        objects = [self.sample[key] for key in ("candidate", "authorization", "reference")]
        objects.append(transition_sample(self.sample["reference"])["transition"])
        for record in objects:
            with self.subTest(route=record["object_kind"]):
                mutated = copy.deepcopy(record)
                mutated["synthetic_extra"] = SENTINELS[0]
                self.assert_failure(bridge.validate_context_bridge_object(mutated, record["object_kind"], self.registry), "context_bridge_schema_invalid", "$")
        self.assert_failure(bridge.validate_context_bridge_object(None, "context_candidate", self.registry), "context_bridge_invalid_object", "$")
        with patch.object(bridge, "SchemaRegistry", side_effect=RuntimeError(SENTINELS[0])):
            self.assert_failure(bridge.validate_context_bridge_object(self.sample["candidate"], "context_candidate"), "context_bridge_validation_unavailable", "$", Decision.ERROR, "validation_unavailable")

    def test_complete_validation_evidence_passes_and_is_immutable(self):
        before = copy.deepcopy(self.sample)
        self.assert_positive(self.validation(), "context_validation_artifact", "validation_chain_valid")
        self.assertEqual(before, self.sample)
        # C/P/V 校验允许不提供 V 的精确字节；完整登记另有要求。
        del self.sample["evidence_context"]["object_bytes"]["validation_artifact"]
        self.assert_positive(self.validation(), "context_validation_artifact", "validation_chain_valid")

    def test_validation_identity_and_fingerprint_linkage(self):
        rows = (
            ("candidate_id", SENTINELS[2], "context_bridge_identity_mismatch"),
            ("proposal_id", SENTINELS[2], "context_bridge_identity_mismatch"),
            ("candidate_fingerprint", fixtures.fingerprint(b"Synthetic P3 changed candidate"), "context_bridge_fingerprint_mismatch"),
            ("proposal_fingerprint", fixtures.fingerprint(b"Synthetic P3 changed proposal"), "context_bridge_fingerprint_mismatch"),
        )
        for field, value, code in rows:
            with self.subTest(field=field):
                sample = copy.deepcopy(self.sample)
                # V 字节在本 API 可选，省略它以单独观察 V 与 C/P 的关联。
                del sample["evidence_context"]["object_bytes"]["validation_artifact"]
                sample["validation_artifact"][field] = value
                self.assert_failure(self.validation(sample), code, "$/validation_artifact/" + field)
        for field, value, code in rows[:1] + rows[2:3]:
            sample = copy.deepcopy(self.sample)
            sample["proposal"][field] = value
            self.assert_failure(self.validation(sample), code, "$/proposal/" + field)

    def test_exact_object_bytes_and_json_representation(self):
        for name in ("candidate", "proposal", "validation_artifact"):
            with self.subTest(object=name):
                sample = copy.deepcopy(self.sample)
                sample["evidence_context"]["object_bytes"][name] = b"{}"
                self.assert_failure(self.validation(sample), "context_bridge_exact_input_mismatch", "$/evidence_context/object_bytes/" + name)
        original = self.sample["evidence_context"]["object_bytes"]["candidate"]
        for blob in (b"\xef\xbb\xbf" + original, b'{"object_kind":"context_candidate","object_kind":"context_candidate"}', b"not JSON"):
            with self.subTest(bytes=blob[:12]):
                sample = copy.deepcopy(self.sample)
                sample["evidence_context"]["object_bytes"]["candidate"] = blob
                self.assert_failure(self.validation(sample), "context_bridge_exact_input_mismatch")
        sample = copy.deepcopy(self.sample)
        sample["evidence_context"]["object_bytes"]["candidate"] = original + b"\n"
        result = self.validation(sample)
        self.assert_failure(result, "context_bridge_fingerprint_mismatch")
        self.assertNotIn("context_bridge_exact_input_mismatch", {issue.code for issue in result.errors})

    def test_review_policy_and_snapshot_linkage(self):
        cases = (
            (("review_evidence_bytes",), b"Synthetic P3 changed review", "context_bridge_review_evidence_mismatch"),
            (("policy", "policy_id"), fixtures.synthetic_id("other-policy"), "context_bridge_policy_mismatch"),
            (("policy", "policy_version"), "synthetic-p3-v2", "context_bridge_policy_mismatch"),
            (("policy", "policy_bytes"), b"Synthetic P3 changed policy", "context_bridge_policy_mismatch"),
            (("existing_snapshot", "snapshot_bytes"), b"Synthetic P3 changed snapshot", "context_bridge_snapshot_mismatch"),
            (("existing_snapshot", "id_index", "snapshot_fingerprint"), fixtures.fingerprint(b"Synthetic P3 other snapshot"), "context_bridge_snapshot_mismatch"),
        )
        for path, value, code in cases:
            with self.subTest(path=path):
                sample = copy.deepcopy(self.sample)
                parent = sample["evidence_context"]
                for key in path[:-1]:
                    parent = parent[key]
                parent[path[-1]] = value
                self.assert_failure(self.validation(sample), code)

    def test_required_evidence_missing_and_closed_context(self):
        for field in ("object_bytes", "review_evidence_bytes", "policy", "existing_snapshot", "source_observations"):
            with self.subTest(field=field):
                sample = copy.deepcopy(self.sample)
                del sample["evidence_context"][field]
                self.assert_failure(self.validation(sample), "context_bridge_missing_context", "$/evidence_context/" + field, Decision.NEEDS_REVIEW, "incomplete_chain")
        sample = copy.deepcopy(self.sample)
        sample["evidence_context"]["synthetic_extra"] = SENTINELS[0]
        self.assert_failure(self.validation(sample), "context_bridge_invalid_object", "$/evidence_context")

    def test_source_observation_fingerprint_and_required_exchange(self):
        sample = copy.deepcopy(self.sample)
        del sample["evidence_context"]["source_observations"][0]["request"]
        self.assert_failure(self.validation(sample), "context_bridge_missing_context", "$/evidence_context/source_observations/0/request", Decision.NEEDS_REVIEW, "incomplete_chain")
        for field, value in (
            ("entry_index", 1),
            ("evidence_bytes", b"{}"),
            ("exact_content_bytes", b"Synthetic P3 other content"),
        ):
            with self.subTest(field=field):
                sample = copy.deepcopy(self.sample)
                sample["evidence_context"]["source_observations"][0][field] = value
                self.assert_failure(self.validation(sample), "context_bridge_source_observation_mismatch")
        sample = copy.deepcopy(self.sample)
        del sample["evidence_context"]["object_bytes"]["validation_artifact"]
        sample["validation_artifact"]["source_observation_fingerprints"][0] = fixtures.fingerprint(b"Synthetic P3 other observation")
        self.assert_failure(self.validation(sample), "context_bridge_source_observation_mismatch", "$/validation_artifact/source_observation_fingerprints/0")
        sample = copy.deepcopy(self.sample)
        sample["evidence_context"]["source_observations"] = []
        self.assert_failure(self.validation(sample), "context_bridge_source_observation_mismatch")

    def test_source_observation_scope_source_and_entry_linkage(self):
        for field in ("expected_scope_id", "source_id", "target_locator"):
            with self.subTest(field=field):
                sample = copy.deepcopy(self.sample)
                observation = sample["evidence_context"]["source_observations"][0]
                if field == "expected_scope_id":
                    observation[field] = fixtures.synthetic_id("other-scope")
                else:
                    observation["request"][field] = fixtures.synthetic_id("other-source") if field == "source_id" else "synthetic:entry:beta"
                    # 显式重新构造此条 Source 响应，使交换内部关联仍然一致。
                    observation["response"] = fixtures.build_source_adapter_result(observation["request"])
                    observation["evidence_bytes"] = fixtures.encode_test_object(observation["response"])
                    sample["validation_artifact"]["source_observation_fingerprints"][0] = fixtures.fingerprint(observation["evidence_bytes"])
                    del sample["evidence_context"]["object_bytes"]["validation_artifact"]
                code = "context_bridge_source_observation_mismatch" if field == "target_locator" else "context_bridge_source_linkage_mismatch"
                self.assert_failure(self.validation(sample), code)

    def test_source_error_is_not_successful_registration_observation(self):
        observation = self.sample["evidence_context"]["source_observations"][0]
        observation["response"] = fixtures.build_source_adapter_error(observation["request"])
        observation["evidence_bytes"] = fixtures.encode_test_object(observation["response"])
        del observation["exact_content_bytes"]
        self.sample["validation_artifact"]["source_observation_fingerprints"] = [fixtures.fingerprint(observation["evidence_bytes"])]
        del self.sample["evidence_context"]["object_bytes"]["validation_artifact"]
        self.assert_failure(self.validation(), "context_bridge_source_observation_not_successful", "$/evidence_context/source_observations/0/response")

    def test_explicit_registration_time_order(self):
        for field, value in (("source_revalidated_at", fixtures.utc_timestamp(0)), ("validated_at", fixtures.utc_timestamp(0))):
            with self.subTest(field=field):
                sample = copy.deepcopy(self.sample)
                del sample["evidence_context"]["object_bytes"]["validation_artifact"]
                sample["validation_artifact"][field] = value
                self.assert_failure(self.validation(sample), "context_bridge_timestamp_inconsistent")
        for object_name, field, value in (("authorization", "authorized_at", fixtures.utc_timestamp(1)), ("reference", "registered_at", fixtures.utc_timestamp(2))):
            with self.subTest(object=object_name):
                sample = copy.deepcopy(self.sample)
                sample[object_name][field] = value
                self.assert_failure(self.chain(sample), "context_bridge_timestamp_inconsistent", "$/" + object_name + "/" + field)

    def test_full_chain_passes_and_inputs_are_immutable(self):
        before = copy.deepcopy(self.sample)
        self.assert_positive(self.chain(), "registered_context_reference", "registration_chain_valid")
        self.assertEqual(before, self.sample)

    def test_proposal_and_validation_do_not_replace_human_evidence(self):
        self.assert_positive(self.validation(), "context_validation_artifact", "validation_chain_valid")
        for missing in ("authorization", "reference"):
            with self.subTest(missing=missing):
                sample = copy.deepcopy(self.sample)
                sample[missing] = None
                self.assert_failure(self.chain(sample), "context_bridge_missing_context", "$/" + missing, Decision.NEEDS_REVIEW, "incomplete_chain")
        sample = copy.deepcopy(self.sample)
        sample["authorization"] = sample["proposal"]
        self.assert_failure(self.chain(sample), "context_bridge_route_mismatch", "$/authorization/object_kind")
        sample = copy.deepcopy(self.sample)
        del sample["evidence_context"]["object_bytes"]["validation_artifact"]
        self.assert_failure(self.chain(sample), "context_bridge_missing_context", "$/evidence_context/object_bytes/validation_artifact", Decision.NEEDS_REVIEW, "incomplete_chain")

    def test_validation_outcome_differs_between_review_and_full_chain(self):
        for outcome, decision, status in (("needs_review", Decision.NEEDS_REVIEW, "incomplete_chain"), ("reject", Decision.REJECT, "rejected")):
            with self.subTest(outcome=outcome):
                sample = copy.deepcopy(self.sample)
                sample["validation_artifact"].update(validation_outcome=outcome, issue_codes=["synthetic_issue"])
                blob = fixtures.encode_test_object(sample["validation_artifact"])
                sample["evidence_context"]["object_bytes"]["validation_artifact"] = blob
                sample["authorization"]["validation_artifact_fingerprint"] = fixtures.fingerprint(blob)
                self.assert_failure(self.validation(sample), "context_bridge_validation_outcome_not_pass", decision=decision, status=status)
                self.assert_failure(self.chain(sample), "context_bridge_validation_outcome_not_pass")

    def test_human_authorization_identity_fingerprint_and_source_links(self):
        for field, value, code in (
            ("validation_artifact_id", SENTINELS[2], "context_bridge_identity_mismatch"),
            ("candidate_id", SENTINELS[2], "context_bridge_identity_mismatch"),
            ("proposal_id", SENTINELS[2], "context_bridge_identity_mismatch"),
            ("validation_artifact_fingerprint", fixtures.fingerprint(b"Synthetic P3 different V"), "context_bridge_fingerprint_mismatch"),
            ("candidate_fingerprint", fixtures.fingerprint(b"Synthetic P3 different C"), "context_bridge_fingerprint_mismatch"),
            ("proposal_fingerprint", fixtures.fingerprint(b"Synthetic P3 different P"), "context_bridge_fingerprint_mismatch"),
            ("context_type", "knowledge", "context_bridge_source_linkage_mismatch"),
            ("source_id", SENTINELS[2], "context_bridge_source_linkage_mismatch"),
            ("final_source_locator", SENTINELS[1], "context_bridge_source_linkage_mismatch"),
        ):
            with self.subTest(field=field):
                sample = copy.deepcopy(self.sample)
                sample["authorization"][field] = value
                self.assert_failure(self.chain(sample), code, "$/authorization/" + field)

    def test_reference_projection_is_exact_and_not_repaired(self):
        rows = (
            ("registration_authorization_id", SENTINELS[2]), ("context_type", "knowledge"),
            ("source_id", SENTINELS[2]), ("status", "paused"), ("retrieval_hint", "Synthetic P3 different hint"),
            ("canonical_name", "Synthetic P3 different name"), ("source_locator", SENTINELS[1]),
            ("source_entry_points", ["synthetic:entry:beta"]), ("access_scope", "restricted"),
            ("allowed_clients", []), ("freshness_policy", "manual_verification"),
            ("provenance_policy", "locator_only"), ("aliases", ["Synthetic P3 alias"]),
        )
        for field, value in rows:
            with self.subTest(field=field):
                sample = copy.deepcopy(self.sample)
                sample["reference"][field] = value
                before = copy.deepcopy(sample)
                self.assert_failure(self.chain(sample), "context_bridge_authorization_projection_mismatch", "$/reference/" + field)
                self.assertEqual(before, sample)

    def test_final_human_choice_can_differ_from_suggestion(self):
        self.sample["authorization"]["final_canonical_name"] = "Synthetic P3 owner-selected name"
        self.sample["reference"]["canonical_name"] = "Synthetic P3 owner-selected name"
        self.sample["authorization"]["final_allowed_clients"] = []
        self.sample["reference"]["allowed_clients"] = []
        self.assert_positive(self.chain(), "registered_context_reference", "registration_chain_valid")

    def test_entry_selection_must_be_an_ordered_subset(self):
        self.sample["authorization"]["final_source_entry_points"] = ["synthetic:entry:beta"]
        self.sample["reference"]["source_entry_points"] = ["synthetic:entry:beta"]
        self.assert_failure(self.chain(), "context_bridge_entry_selection_mismatch", "$/authorization/final_source_entry_points")

    def test_two_observations_allow_narrowing_but_not_entry_reordering(self):
        sample = copy.deepcopy(self.sample)
        sample["proposal"]["suggested_source_entry_points"].append("synthetic:entry:beta")
        second = copy.deepcopy(sample["evidence_context"]["source_observations"][0])
        second["entry_index"] = 1
        second["request"]["request_id"] = fixtures.synthetic_id("source-request", 2)
        second["request"]["target_locator"] = "synthetic:entry:beta"
        second["response"] = fixtures.build_source_adapter_result(second["request"])
        second["evidence_bytes"] = fixtures.encode_test_object(second["response"])
        sample["evidence_context"]["source_observations"].append(second)
        # 明确构造新的正向二入口证据，不修改 P3A helper 或自动修复待测反例。
        proposal_bytes = fixtures.encode_test_object(sample["proposal"])
        sample["evidence_context"]["object_bytes"]["proposal"] = proposal_bytes
        sample["validation_artifact"]["proposal_fingerprint"] = fixtures.fingerprint(proposal_bytes)
        sample["validation_artifact"]["source_observation_fingerprints"].append(fixtures.fingerprint(second["evidence_bytes"]))
        validation_bytes = fixtures.encode_test_object(sample["validation_artifact"])
        sample["evidence_context"]["object_bytes"]["validation_artifact"] = validation_bytes
        sample["authorization"]["proposal_fingerprint"] = fixtures.fingerprint(proposal_bytes)
        sample["authorization"]["validation_artifact_fingerprint"] = fixtures.fingerprint(validation_bytes)
        self.assert_positive(self.chain(sample), "registered_context_reference", "registration_chain_valid")
        reversed_entries = ["synthetic:entry:beta", fixtures.SYNTHETIC_ENTRY]
        sample["authorization"]["final_source_entry_points"] = list(reversed_entries)
        sample["reference"]["source_entry_points"] = list(reversed_entries)
        self.assert_failure(self.chain(sample), "context_bridge_entry_selection_mismatch", "$/authorization/final_source_entry_points")

    def test_reference_index_missing_or_already_registered(self):
        sample = copy.deepcopy(self.sample)
        del sample["evidence_context"]["existing_snapshot"]["id_index"]
        self.assert_failure(self.chain(sample), "context_bridge_missing_context", "$/evidence_context/existing_snapshot/id_index", Decision.NEEDS_REVIEW, "incomplete_chain")
        sample = copy.deepcopy(self.sample)
        sample["evidence_context"]["existing_snapshot"]["id_index"]["reference_ids"] = [sample["reference"]["reference_id"]]
        self.assert_failure(self.chain(sample), "context_bridge_reference_already_exists", "$/reference/reference_id")

    def test_transition_positive_and_input_immutability(self):
        sample = transition_sample(self.sample["reference"])
        before = copy.deepcopy(sample)
        self.assert_positive(bridge.validate_reference_transition(**sample, registry=self.registry), "context_reference_transition", "transition_valid")
        self.assertEqual(before, sample)

    def test_transition_event_identity_fingerprints_and_states(self):
        rows = (
            ("reference_id", SENTINELS[2], "context_bridge_identity_mismatch"),
            ("previous_reference_fingerprint", fixtures.fingerprint(b"Synthetic P3 previous"), "context_bridge_fingerprint_mismatch"),
            ("new_reference_fingerprint", fixtures.fingerprint(b"Synthetic P3 next"), "context_bridge_fingerprint_mismatch"),
            ("from_status", "source_unavailable", "context_bridge_transition_state_mismatch"),
            ("to_status", "archived", "context_bridge_transition_state_mismatch"),
        )
        for field, value, code in rows:
            with self.subTest(field=field):
                sample = transition_sample(self.sample["reference"])
                sample["transition"][field] = value
                self.assert_failure(bridge.validate_reference_transition(**sample, registry=self.registry), code, "$/transition/" + field)
        sample = transition_sample(self.sample["reference"])
        sample["transition"]["to_status"] = "active"
        self.assert_failure(bridge.validate_reference_transition(**sample, registry=self.registry), "context_bridge_schema_invalid", "$/transition")

    def test_transition_immutable_fields_with_explicitly_rebound_bytes(self):
        rows = (
            ("reference_id", SENTINELS[2]), ("context_type", "knowledge"),
            ("canonical_name", "Synthetic P3 other name"), ("source_id", SENTINELS[2]),
            ("source_locator", SENTINELS[1]), ("source_entry_points", ["synthetic:entry:beta"]),
            ("allowed_clients", []), ("access_scope", "restricted"),
            ("freshness_policy", "manual_verification"), ("provenance_policy", "locator_only"),
            ("registration_authorization_id", SENTINELS[2]), ("retrieval_hint", "Synthetic P3 changed hint"),
            ("registered_at", fixtures.utc_timestamp(5)), ("last_verified_at", fixtures.utc_timestamp(2)),
            ("verification_evidence_id", fixtures.synthetic_id("other-observation")),
            ("aliases", ["Synthetic P3 alias"]),
        )
        for field, value in rows:
            with self.subTest(field=field):
                sample = transition_sample(self.sample["reference"])
                sample["new_reference"][field] = value
                # 有意同步新对象字节与事件指纹，仅隔离不可变字段判断。
                blob = fixtures.encode_test_object(sample["new_reference"])
                sample["evidence_context"]["object_bytes"]["new_reference"] = blob
                sample["transition"]["new_reference_fingerprint"] = fixtures.fingerprint(blob)
                self.assert_failure(bridge.validate_reference_transition(**sample, registry=self.registry), "context_bridge_immutable_binding_changed", "$/new_reference")

    def test_transition_exact_bytes_history_and_time(self):
        sample = transition_sample(self.sample["reference"])
        sample["evidence_context"]["object_bytes"]["new_reference"] = b"{}"
        self.assert_failure(bridge.validate_reference_transition(**sample, registry=self.registry), "context_bridge_exact_input_mismatch", "$/evidence_context/object_bytes/new_reference")
        sample = transition_sample(self.sample["reference"])
        sample["evidence_context"]["transition_history"] = {
            "transition_ids": [],
            "current_reference_bytes": sample["evidence_context"]["object_bytes"]["previous_reference"],
            "last_transitioned_at": fixtures.utc_timestamp(6),
        }
        self.assert_positive(bridge.validate_reference_transition(**sample, registry=self.registry), "context_reference_transition", "transition_valid")
        sample["evidence_context"]["transition_history"]["transition_ids"] = [sample["transition"]["transition_id"]]
        self.assert_failure(bridge.validate_reference_transition(**sample, registry=self.registry), "context_bridge_transition_replay_detected", "$/transition/transition_id")
        sample = transition_sample(self.sample["reference"])
        sample["transition"]["transitioned_at"] = fixtures.utc_timestamp(3)
        self.assert_failure(bridge.validate_reference_transition(**sample, registry=self.registry), "context_bridge_timestamp_inconsistent", "$/transition/transitioned_at")

    def test_priority_reject_over_missing_context(self):
        result = bridge.validate_registration_validation({"object_kind": "synthetic_wrong"}, None, None, registry=self.registry)
        self.assert_failure(result, "context_bridge_route_mismatch", "$/candidate/object_kind")
        self.assertIn("context_bridge_missing_context", {issue.code for issue in result.errors})

    def test_priority_reject_over_observed_validation_unavailable(self):
        # C 在分流阶段产生矛盾，P/V 的真实严格校验调用随后遭遇不可用。
        with patch.object(self.registry, "validator_for", side_effect=RuntimeError(SENTINELS[0])) as strict:
            result = bridge.validate_registration_validation({"object_kind": "synthetic_wrong"}, self.sample["proposal"], self.sample["validation_artifact"], registry=self.registry)
        self.assertTrue(strict.called)
        self.assert_failure(result, "context_bridge_route_mismatch")
        self.assertIn("context_bridge_validation_unavailable", {issue.code for issue in result.errors})

    def test_priority_error_over_missing_context(self):
        for failure, code in ((RuntimeError(SENTINELS[0]), "context_bridge_validation_unavailable"), (MemoryError(SENTINELS[0]), "context_bridge_resource_limit_exceeded")):
            with self.subTest(error=type(failure).__name__), patch.object(self.registry, "validator_for", side_effect=failure) as strict:
                result = bridge.validate_registration_validation(self.sample["candidate"], None, None, registry=self.registry)
            self.assertTrue(strict.called)
            self.assert_failure(result, code, decision=Decision.ERROR, status="validation_unavailable")
            self.assertIn("context_bridge_missing_context", {issue.code for issue in result.errors})

    def test_supplied_registry_reaches_source_delegates(self):
        with patch.object(bridge, "SchemaRegistry", side_effect=AssertionError("unexpected registry")) as bridge_factory, patch.object(source, "SchemaRegistry", side_effect=AssertionError("unexpected registry")) as source_factory, patch.object(bridge, "validate_source_adapter_object", wraps=bridge.validate_source_adapter_object) as objects, patch.object(bridge, "validate_source_adapter_exchange", wraps=bridge.validate_source_adapter_exchange) as exchange:
            self.assert_positive(self.validation(), "context_validation_artifact", "validation_chain_valid")
            self.assert_positive(self.chain(), "registered_context_reference", "registration_chain_valid")
            self.assert_positive(bridge.validate_context_bridge_object(self.sample["candidate"], "context_candidate", self.registry), "context_candidate", "object_valid")
            self.assert_positive(bridge.validate_reference_transition(**transition_sample(self.sample["reference"]), registry=self.registry), "context_reference_transition", "transition_valid")
        bridge_factory.assert_not_called()
        source_factory.assert_not_called()
        self.assertEqual(6, objects.call_count)
        self.assertEqual(2, exchange.call_count)
        self.assertTrue(all(item.args[2] is self.registry for item in objects.call_args_list))
        self.assertTrue(all(item.kwargs["registry"] is self.registry for item in exchange.call_args_list))

    def test_diagnostics_do_not_echo_private_sentinels(self):
        for field, value in (("canonical_name", SENTINELS[0]), ("source_locator", SENTINELS[1]), ("source_id", SENTINELS[2])):
            with self.subTest(field=field):
                sample = copy.deepcopy(self.sample)
                sample["reference"][field] = value
                self.assert_failure(self.chain(sample), "context_bridge_authorization_projection_mismatch")
        sample = copy.deepcopy(self.sample)
        observation = sample["evidence_context"]["source_observations"][0]
        observation["response"] = fixtures.build_source_adapter_result(observation["request"], text=SENTINELS[0])
        observation["response"]["payload"]["byte_count"] += 1
        self.assert_failure(self.validation(sample), "context_bridge_source_observation_mismatch")


if __name__ == "__main__":
    unittest.main()
