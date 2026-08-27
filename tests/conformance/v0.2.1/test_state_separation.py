import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "tests/fixtures/v0.2.1/state-separation"
ASSESSMENT_FIXTURES = ROOT / "tests/fixtures/v0.2/pre-execution-assessment"
SCHEMA = json.loads((ROOT / "schemas/v0.2.1/state-separation.schema.json").read_text())

sys.path.insert(0, str(ROOT / "tests/support"))
from state_separation_semantics_v021 import (  # noqa: E402
    execute_transition_errors,
    state_record_errors,
)
from strict_schema_validation import strict_validator  # noqa: E402

VALIDATOR = strict_validator(SCHEMA)


def load(path):
    return json.loads(path.read_text())


def load_transition(name):
    return load(FIXTURES / name)


def required_context():
    transition = load_transition("execute-required-valid.json")
    action = load(ASSESSMENT_FIXTURES / "action-low-risk-valid.json")
    assessment = load(
        ASSESSMENT_FIXTURES / "assessment-ready-existing-authorization-valid.json"
    )
    return transition, {assessment["record_id"]: assessment}, {action["record_id"]: action}


def not_required_context():
    transition = load_transition("execute-not-required-valid.json")
    action = load(ASSESSMENT_FIXTURES / "action-low-risk-valid.json")
    action["record_id"] = "action-public-read"
    action["target_ref"] = {
        "target_id": "public-document",
        "target_type": "synthetic-public-document",
        "target_version": "1.0",
        "observed_state_ref": "state-public-source",
    }
    action["authorization_requirement"] = {
        "required": False,
        "authority_type": "none",
        "scope_requirements": [],
    }
    action["authorization_refs"] = []
    assessment = load(
        ASSESSMENT_FIXTURES
        / "assessment-ready-authorization-not-required-valid.json"
    )
    return transition, {assessment["record_id"]: assessment}, {action["record_id"]: action}


class StateSeparationV021Tests(unittest.TestCase):
    def assert_schema_valid(self, record):
        self.assertEqual([], list(VALIDATOR.iter_errors(record)))

    def assert_execute_valid(self, transition, assessments, actions):
        self.assert_schema_valid(transition)
        self.assertEqual(
            [], execute_transition_errors(transition, assessments, actions)
        )

    def test_schema_is_valid_and_has_distinct_identity(self):
        self.assertIsNotNone(strict_validator(SCHEMA).format_checker)
        self.assertEqual(
            "urn:xingshu:core:schema:v0.2.1:state-separation", SCHEMA["$id"]
        )

    def test_g1_not_required_with_empty_authorization_refs_passes(self):
        # Case 1: authorization not required is a valid, explicit outcome.
        self.assert_execute_valid(*not_required_context())

    def test_g1_required_with_valid_authorization_passes(self):
        # Case 2: the transition, assessment, and action chain agrees.
        self.assert_execute_valid(*required_context())

    def test_g1_required_with_empty_authorization_refs_rejects(self):
        # Case 3: an authorization-required action cannot use empty refs.
        transition, assessments, actions = required_context()
        transition["authorization_refs"] = []
        self.assertIn(
            "authorization_missing",
            execute_transition_errors(transition, assessments, actions),
        )

    def test_g1_missing_assessment_fails_closed(self):
        # Case 4: the schema requires assessment_ref for execute.
        transition, assessments, actions = required_context()
        del transition["assessment_ref"]
        self.assertTrue(list(VALIDATOR.iter_errors(transition)))
        self.assertEqual(
            ["assessment_missing"],
            execute_transition_errors(transition, assessments, actions),
        )

    def test_g1_assessment_reference_identity_mismatch_fails_closed(self):
        transition, assessments, actions = required_context()
        self.assertEqual(
            [], execute_transition_errors(transition, assessments, actions)
        )

        assessment = assessments[transition["assessment_ref"]]
        assessment["record_id"] = "assessment-other-id"
        self.assertEqual(
            ["assessment_reference_mismatch"],
            execute_transition_errors(transition, assessments, actions),
        )

    def test_g1_unknown_or_unresolved_assessment_fails_closed(self):
        # Case 5: unresolved and unknown outcomes are never guessed as valid.
        transition, assessments, actions = required_context()
        transition["assessment_ref"] = "assessment-unresolved"
        self.assertEqual(
            ["assessment_unresolved"],
            execute_transition_errors(transition, assessments, actions),
        )

        transition, assessments, actions = required_context()
        assessment = assessments[transition["assessment_ref"]]
        assessment["authorization_evaluation"]["status"] = "unknown"
        errors = execute_transition_errors(transition, assessments, actions)
        self.assertIn("authorization_unknown", errors)
        self.assertIn("authorization_requirement_mismatch", errors)

    def test_g1_expired_assessment_fails_closed(self):
        # Case 6: transition time is outside the assessment validity window.
        transition, assessments, actions = required_context()
        transition["occurred_at"] = "2026-01-01T02:00:00Z"
        self.assertIn(
            "assessment_expired",
            execute_transition_errors(transition, assessments, actions),
        )

    def test_g1_scope_and_action_mismatch_fail_closed(self):
        # Case 7: both assessment target and action source association matter.
        transition, assessments, actions = required_context()
        assessments[transition["assessment_ref"]]["target_state_ref"] = "state-other"
        self.assertIn(
            "assessment_target_mismatch",
            execute_transition_errors(transition, assessments, actions),
        )

        transition, assessments, actions = required_context()
        actions["action-low-risk"]["target_ref"]["observed_state_ref"] = "state-other"
        self.assertIn(
            "action_transition_mismatch",
            execute_transition_errors(transition, assessments, actions),
        )

    def test_g1_stale_authorization_fails_closed(self):
        # Case 8: stale is a denial state, not a warning.
        transition, assessments, actions = required_context()
        authorization = assessments[transition["assessment_ref"]][
            "authorization_evaluation"
        ]
        authorization["status"] = "stale"
        authorization["freshness"] = "stale"
        self.assertIn(
            "authorization_stale",
            execute_transition_errors(transition, assessments, actions),
        )

    def test_g1_out_of_scope_authorization_fails_closed(self):
        # Case 9: out-of-scope authorization cannot support execution.
        transition, assessments, actions = required_context()
        authorization = assessments[transition["assessment_ref"]][
            "authorization_evaluation"
        ]
        authorization["status"] = "out_of_scope"
        authorization["scope_match"] = "mismatch"
        self.assertIn(
            "authorization_out_of_scope",
            execute_transition_errors(transition, assessments, actions),
        )

    def test_g1_action_requirement_and_other_gates_remain_enforced(self):
        transition, assessments, actions = required_context()
        actions["action-low-risk"]["authorization_requirement"]["required"] = False
        self.assertIn(
            "authorization_requirement_mismatch",
            execute_transition_errors(transition, assessments, actions),
        )

        mutations = [
            ("risk_evaluation", "result", "fail", "risk_evaluation_not_passed"),
            ("privacy_evaluation", "result", "unknown", "privacy_evaluation_not_passed"),
            ("reversibility_evaluation", "result", "needs_review", "reversibility_evaluation_not_passed"),
            ("evidence_plan_evaluation", "result", "fail", "evidence_plan_evaluation_not_passed"),
        ]
        for section, field, value, expected in mutations:
            with self.subTest(gate=section):
                transition, assessments, actions = required_context()
                assessments[transition["assessment_ref"]][section][field] = value
                self.assertIn(
                    expected,
                    execute_transition_errors(transition, assessments, actions),
                )

        transition, assessments, actions = required_context()
        assessments[transition["assessment_ref"]]["stop_condition_state"] = "triggered"
        self.assertIn(
            "stop_condition_not_clear",
            execute_transition_errors(transition, assessments, actions),
        )

        transition, assessments, actions = required_context()
        assessments[transition["assessment_ref"]]["assessment_outcome"] = "blocked"
        self.assertIn(
            "assessment_not_ready",
            execute_transition_errors(transition, assessments, actions),
        )

        transition, assessments, actions = required_context()
        transition["condition_results"][0]["result"] = "unknown"
        self.assertIn(
            "assessment_condition_not_satisfied",
            execute_transition_errors(transition, assessments, actions),
        )

    def test_g2_runtime_verified_and_stably_verified_are_valid_readbacks(self):
        # Cases 10 and 11: these values verify runtime/readback state only.
        runtime = load_transition("runtime-verified-valid.json")
        for validation_state in ["verified", "stably_verified"]:
            with self.subTest(validation_state=validation_state):
                candidate = copy.deepcopy(runtime)
                candidate["validation_state"] = validation_state
                self.assert_schema_valid(candidate)
                self.assertEqual([], state_record_errors(candidate))

    def test_g2_runtime_verification_does_not_create_outcome(self):
        # Case 12: no outcome record is inferred or embedded.
        runtime = load_transition("runtime-verified-valid.json")
        self.assertNotIn("verification_outcome", runtime)
        self.assertEqual([], state_record_errors(runtime))

        runtime["verification_outcome"] = "verified"
        self.assertTrue(list(VALIDATOR.iter_errors(runtime)))
        self.assertIn(
            "runtime_cannot_claim_outcome_verification", state_record_errors(runtime)
        )


if __name__ == "__main__":
    unittest.main()
