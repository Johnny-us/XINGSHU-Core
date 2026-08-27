import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests/support"))
from strict_schema_validation import strict_validator  # noqa: E402

FIXTURES = ROOT / "tests/fixtures/v0.2/pre-execution-assessment"
SCHEMA = json.loads((ROOT / "schemas/v0.2/pre-execution-assessment.schema.json").read_text())
VALIDATOR = strict_validator(SCHEMA)


def load(name):
    return json.loads((FIXTURES / name).read_text())


def ready_conditions(record):
    auth = record["authorization_evaluation"]
    authorization_ok = auth["status"] == "not_required" or (auth["status"] == "valid" and auth["scope_match"] == "match" and auth["freshness"] == "current" and auth["authorization_refs"])
    evaluations = [record[name]["result"] for name in ("risk_evaluation", "privacy_evaluation", "reversibility_evaluation", "evidence_plan_evaluation")]
    return authorization_ok and all(value == "pass" for value in evaluations) and record["stop_condition_state"] == "clear"


class PreExecutionAssessmentTests(unittest.TestCase):
    def assert_schema_valid(self, name):
        data = load(name)
        self.assertEqual([], list(VALIDATOR.iter_errors(data)), name)
        return data

    def test_action_and_ready_assessments(self):
        self.assert_schema_valid("action-low-risk-valid.json")
        for name in ["assessment-ready-existing-authorization-valid.json", "assessment-ready-authorization-not-required-valid.json", "assessment-ready-no-authorization-effect.json"]:
            record = self.assert_schema_valid(name)
            self.assertTrue(ready_conditions(record), name)
            self.assertEqual("ready_for_execution", record["assessment_outcome"])
            self.assertEqual("none", record["authorization_effect"])

    def test_assessment_fail_closed_routes(self):
        expected = {
            "assessment-missing-authorization.json": "needs_authorization",
            "assessment-stale-authorization.json": "needs_authorization",
            "assessment-missing-evidence.json": "needs_more_evidence",
            "assessment-governance-conflict.json": "deny",
            "assessment-privacy-violation.json": "deny",
            "assessment-stop-triggered.json": "blocked",
        }
        for name, outcome in expected.items():
            record = self.assert_schema_valid(name)
            self.assertEqual(outcome, record["assessment_outcome"], name)
            self.assertFalse(ready_conditions(record), name)
        critical = self.assert_schema_valid("assessment-critical-unknown.json")
        self.assertNotEqual("ready_for_execution", critical["assessment_outcome"])

    def test_execution_boundaries_and_idempotency(self):
        outcomes = {
            "execution-pending-verification-valid.json": "executed_pending_verification",
            "execution-target-drift-stopped.json": "stopped",
            "execution-idempotent-retry-suppressed.json": "duplicate_suppressed",
            "execution-expired-assessment-not-started.json": "not_started",
        }
        for name, outcome in outcomes.items():
            record = self.assert_schema_valid(name)
            self.assertEqual(outcome, record["execution_outcome"])
        conflict = self.assert_schema_valid("execution-idempotency-conflict.json")
        self.assertEqual("idempotency_conflict", conflict["error_code"])
        self.assertEqual("blocked", conflict["safe_next_state"])

    def test_verification_is_distinct_from_command_success(self):
        expected = {
            "verification-valid.json": "verified",
            "verification-command-success-business-fail.json": "verification_failed",
            "verification-partial.json": "partially_verified",
            "verification-stability-single-observation.json": "verified",
            "verification-stable-repeated.json": "verified",
        }
        for name, outcome in expected.items():
            record = self.assert_schema_valid(name)
            self.assertEqual(outcome, record["verification_outcome"], name)
            if outcome == "verified":
                self.assertTrue(all(item["result"] == "pass" for item in record["criterion_results"]))

    def test_unknown_error_code_fails_closed(self):
        record = load("execution-idempotency-conflict.json")
        record["error_code"] = "retry_as_success"
        self.assertTrue(list(VALIDATOR.iter_errors(record)))


if __name__ == "__main__":
    unittest.main()
